from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import logging
from pathlib import Path
from typing import Optional
import asyncio
import aiohttp
import boto3
import subprocess
from botocore.config import Config
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

QB_HOST = os.getenv("QB_HOST", "localhost")
QB_PORT = int(os.getenv("QB_PORT", "8080"))
QB_USERNAME = os.getenv("QB_USERNAME", "admin")
QB_PASSWORD = os.getenv("QB_PASSWORD", "adminadmin")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/downloads")

# Cloudflare R2 config (optional)
R2_ENABLED = os.getenv("R2_ENABLED", "false").lower() == "true"
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_BUCKET = os.getenv("R2_BUCKET", "torrent-media")

# FFmpeg/transcoding config
TRANSCODE_CACHE_DIR = os.getenv("TRANSCODE_CACHE_DIR", "/tmp/transcode-cache")
TRANSCODE_TIMEOUT = 600  # 10 minutes
TRANSCODE_PRESET = "ultrafast"  # fast transcoding
TRANSCODE_BITRATE = "3000k"

qb_url = f"http://{QB_HOST}:{QB_PORT}"
qb_session = None

r2_client = None
if R2_ENABLED:
    r2_client = boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(s3={'addressing_style': 'virtual'})
    )

# Create cache directory
Path(TRANSCODE_CACHE_DIR).mkdir(parents=True, exist_ok=True)

# ============================================================================
# MODELS
# ============================================================================

class TorrentRequest(BaseModel):
    magnet: str
    save_path: Optional[str] = None
    stream_to_r2: bool = False

class TorrentStatus(BaseModel):
    name: str
    state: str
    progress: float
    total_size: int
    downloaded: int
    download_speed: int
    upload_speed: int
    peers: int
    seeds: int
    eta: int

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

async def check_ffmpeg():
    """Check if ffmpeg is available"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False

def transcode_to_mp4(input_path: str, output_path: str) -> bool:
    """Transcode media file to MP4 using FFmpeg"""
    try:
        logger.info(f"Starting transcode: {input_path} -> {output_path}")
        
        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-c:v", "libx264",
            "-preset", TRANSCODE_PRESET,
            "-b:v", TRANSCODE_BITRATE,
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-y",
            output_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=TRANSCODE_TIMEOUT,
            text=True
        )
        
        if result.returncode == 0:
            logger.info(f"Transcode succeeded: {output_path}")
            return True
        else:
            logger.error(f"FFmpeg error: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"Transcode timeout")
        return False
    except Exception as e:
        logger.error(f"Transcode error: {e}")
        return False


def needs_transcoding(file_path: str) -> bool:
    """Check if file needs transcoding for browser compatibility"""
    transcode_formats = ["mkv", "avi", "flv", "wmv", "m2ts", "ts", "mts"]
    
    ext = Path(file_path).suffix.lower().lstrip(".")
    return ext in transcode_formats

# ============================================================================
# QBITTORRENT API CLIENT
# ============================================================================

async def qb_request(method: str, endpoint: str, data: dict = None):
    """Make authenticated request to qBittorrent API"""
    global qb_session
    
    if qb_session is None:
        logger.error("qBittorrent session not initialized")
        return None
    
    try:
        url = f"{qb_url}/api/v2{endpoint}"
        auth = aiohttp.BasicAuth(QB_USERNAME, QB_PASSWORD)
        
        if method == "GET":
            async with qb_session.get(
                url,
                params=data,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    try:
                        return await resp.json()
                    except:
                        return {"status": "ok"}
                elif resp.status == 403:
                    logger.error(f"Authentication failed for {endpoint}")
                    return None
                elif resp.status == 404:
                    logger.warning(f"Endpoint not found (404): {endpoint}")
                    return None
                else:
                    logger.warning(f"qB API returned {resp.status}")
                    return None
                    
        elif method == "POST":
            async with qb_session.post(
                url,
                data=data,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    try:
                        return await resp.json()
                    except:
                        return {"status": "ok"}
                elif resp.status == 403:
                    logger.error(f"Authentication failed")
                    return None
                else:
                    logger.warning(f"qB API returned {resp.status}")
                    return None
                    
        elif method == "DELETE":
            async with qb_session.delete(
                url,
                params=data,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    try:
                        return await resp.json()
                    except:
                        return {"status": "ok"}
                else:
                    logger.warning(f"qB API returned {resp.status}")
                    return None
                    
    except asyncio.TimeoutError:
        logger.error(f"Timeout on {method} {endpoint}")
        return None
    except Exception as e:
        logger.error(f"qB request error: {e}")
        return None

# ============================================================================
# FASTAPI LIFESPAN
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global qb_session
    
    logger.info("Starting application...")
    
    # Check FFmpeg
    has_ffmpeg = await check_ffmpeg()
    if has_ffmpeg:
        logger.info("✅ FFmpeg available for transcoding")
    else:
        logger.warning("⚠️  FFmpeg not found - transcoding disabled")
    
    # Try to connect to qBittorrent
    for attempt in range(10):
        session = None
        try:
            logger.info(f"Checking qBittorrent at {qb_url} (attempt {attempt+1}/10)")
            
            session = aiohttp.ClientSession()
            auth = aiohttp.BasicAuth(QB_USERNAME, QB_PASSWORD)
            
            async with session.get(
                f"{qb_url}/api/v2/app/webapiVersion",
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    version = await resp.text()
                    logger.info(f"✅ Connected to qBittorrent API v{version}")
                    qb_session = session
                    break
                elif resp.status == 403:
                    logger.error(f"❌ Authentication failed")
                    if session:
                        await session.close()
                else:
                    logger.warning(f"qBittorrent returned {resp.status}")
                    if session:
                        await session.close()
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} failed: {e}")
            if session:
                await session.close()
        
        if attempt < 9:
            await asyncio.sleep(2)
    
    if qb_session is None:
        logger.error("❌ Failed to connect to qBittorrent")
    
    yield
    
    logger.info("Shutting down...")
    if qb_session:
        await qb_session.close()

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/health")
async def health():
    """Health check endpoint"""
    if qb_session is None:
        raise HTTPException(status_code=503, detail="qBittorrent not connected")
    
    result = await qb_request("GET", "/app/webapiVersion")
    if result:
        r2_status = "connected" if R2_ENABLED and r2_client else "disabled"
        ffmpeg_status = "available" if await check_ffmpeg() else "unavailable"
        return {
            "status": "ok",
            "client": "qbittorrent",
            "r2": r2_status,
            "ffmpeg": ffmpeg_status
        }
    raise HTTPException(status_code=503, detail="qBittorrent not responding")

@app.post("/torrent/add")
async def add_torrent(req: TorrentRequest):
    """Add a torrent via magnet link"""
    save_path = req.save_path or DOWNLOAD_DIR
    
    data = {
        "urls": req.magnet,
        "savepath": save_path,
        "paused": "false"
    }
    
    result = await qb_request("POST", "/torrents/add", data)
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to add torrent")
    
    import re
    hash_match = re.search(r'xt=urn:btih:([a-zA-Z0-9]+)', req.magnet)
    if hash_match:
        magnet_hash = hash_match.group(1)
        
        for i in range(5):
            await asyncio.sleep(1)
            torrents = await qb_request("GET", "/torrents/info", {"hashes": magnet_hash})
            
            if torrents and len(torrents) > 0:
                t = torrents[0]

                await qb_request(
                    "POST",
                    "/torrents/toggleSequentialDownload",
                    {"hashes": t.get("hash")}
                )

                await qb_request(
                    "POST",
                    "/torrents/toggleFirstLastPiecePrio",
                    {"hashes": t.get("hash")}
                )

                return {
                    "hash": t.get("hash"),
                    "name": t.get("name"),
                    "status": "added",
                    "stream_to_r2": req.stream_to_r2 and R2_ENABLED
                }
        
        raise HTTPException(status_code=500, detail="Torrent added but not found")
    else:
        raise HTTPException(status_code=400, detail="Could not extract hash")

@app.get("/torrent/{torrent_hash}/status")
async def get_torrent_status(torrent_hash: str):
    """Get status of a torrent"""
    torrents = await qb_request("GET", "/torrents/info", {"hashes": torrent_hash})
    
    if not torrents or len(torrents) == 0:
        raise HTTPException(status_code=404, detail="Torrent not found")
    
    t = torrents[0]
    return TorrentStatus(
        name=t.get("name", ""),
        state=t.get("state", ""),
        progress=t.get("progress", 0),
        total_size=t.get("total_size", 0),
        downloaded=t.get("downloaded", 0),
        download_speed=t.get("dl_speed", 0),
        upload_speed=t.get("up_speed", 0),
        peers=t.get("peers_total", 0),
        seeds=t.get("seeds_total", 0),
        eta=t.get("eta", 0)
    )

@app.get("/torrent/{torrent_hash}/files")
async def get_torrent_files(torrent_hash: str):
    """Get list of files in a torrent"""
    torrents = await qb_request("GET", "/torrents/info", {"hashes": torrent_hash})
    
    if not torrents:
        raise HTTPException(status_code=404, detail="Torrent not found")
    
    t = torrents[0]
    
    if t.get("state") == "metaDL":
        raise HTTPException(status_code=425, detail="Metadata downloading")
    
    files = await qb_request("GET", "/torrents/files", {"hash": torrent_hash})
    
    if files is None:
        raise HTTPException(status_code=404, detail="Torrent not found")
    
    return [
        {
            "name": f.get("name", ""),
            "size": f.get("size", 0),
            "progress": f.get("progress", 0),
            "path": f.get("name", "")
        }
        for f in files
    ]

@app.get("/torrent/{torrent_hash}/file/{file_path:path}")
async def stream_file(torrent_hash: str, file_path: str, use_r2: bool = False):
    """Stream a file from a torrent (auto-transcode if needed)"""
    torrents = await qb_request("GET", "/torrents/info", {"hashes": torrent_hash})
    
    if not torrents or len(torrents) == 0:
        raise HTTPException(status_code=404, detail="Torrent not found")
    
    t = torrents[0]
    
    if t.get("state") == "metaDL":
        raise HTTPException(status_code=425, detail="Metadata downloading")
    
    base_dir = Path(t.get("save_path", "")).resolve()
    
    try:
        requested_path = (base_dir / file_path).resolve()
    except Exception as e:
        logger.warning(f"Path resolution failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid path")
    
    if not str(requested_path).startswith(str(base_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Wait for file to exist
    max_wait = 30
    elapsed = 0
    
    while elapsed < max_wait:
        if requested_path.exists():
            logger.info(f"File found: {requested_path}")
            break
        
        await asyncio.sleep(0.5)
        elapsed += 0.5
    
    if not requested_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # ✅ KEY FIX: Auto-transcode if needed
    if needs_transcoding(file_path):
        logger.info(f"Auto-transcoding required: {file_path}")
        return await transcode_file(torrent_hash, file_path)
    
    # R2 streaming (for pre-transcoded/compatible files)
    if use_r2 and R2_ENABLED and r2_client:
        r2_key = f"{torrent_hash}/{file_path}"
        
        try:
            r2_client.head_object(Bucket=R2_BUCKET, Key=r2_key)
            logger.info(f"Streaming from R2: {r2_key}")
            
            response = r2_client.get_object(Bucket=R2_BUCKET, Key=r2_key)
            return StreamingResponse(
                response['Body'].iter_chunks(8192),
                media_type="application/octet-stream",
                headers={"Content-Disposition": f"inline; filename={Path(file_path).name}"}
            )
        except:
            logger.info(f"Uploading to R2: {r2_key}")
            
            try:
                with open(requested_path, 'rb') as f:
                    r2_client.upload_fileobj(f, R2_BUCKET, r2_key)
                
                response = r2_client.get_object(Bucket=R2_BUCKET, Key=r2_key)
                return StreamingResponse(
                    response['Body'].iter_chunks(8192),
                    media_type="application/octet-stream",
                    headers={"Content-Disposition": f"inline; filename={Path(file_path).name}"}
                )
            except Exception as e:
                logger.error(f"R2 upload failed: {e}")
                raise HTTPException(status_code=500, detail="R2 upload failed")
    
    # Stream from local storage (MP4, WebM, etc.)
    try:
        return FileResponse(
            requested_path,
            media_type="application/octet-stream",
            filename=requested_path.name
        )
    except Exception as e:
        logger.error(f"Failed to stream: {e}")
        raise HTTPException(status_code=500, detail="Failed to stream")

@app.get("/torrent/{torrent_hash}/file/{file_path:path}/transcode")
async def transcode_file(torrent_hash: str, file_path: str):
    """Transcode and stream a file (MKV, AVI, etc.) as MP4"""
    
    # Check FFmpeg
    has_ffmpeg = await check_ffmpeg()
    if not has_ffmpeg:
        raise HTTPException(
            status_code=503,
            detail="FFmpeg not available. Cannot transcode."
        )
    
    # Get torrent
    torrents = await qb_request("GET", "/torrents/info", {"hashes": torrent_hash})
    if not torrents or len(torrents) == 0:
        raise HTTPException(status_code=404, detail="Torrent not found")
    
    t = torrents[0]
    base_dir = Path(t.get("save_path", "")).resolve()
    
    # Validate path
    try:
        requested_path = (base_dir / file_path).resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path")
    
    if not str(requested_path).startswith(str(base_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Wait for file
    max_wait = 30
    elapsed = 0
    
    while elapsed < max_wait:
        if requested_path.exists():
            logger.info(f"Source file found: {requested_path}")
            break
        await asyncio.sleep(0.5)
        elapsed += 0.5
    
    if not requested_path.exists():
        raise HTTPException(status_code=404, detail="Source file not found")
    
    # Check cache
    cache_key = f"{torrent_hash}_{file_path.replace('/', '_')}.mp4"
    cached_mp4 = Path(TRANSCODE_CACHE_DIR) / cache_key
    
    if cached_mp4.exists():
        logger.info(f"Using cached transcode: {cached_mp4}")
        return FileResponse(
            cached_mp4,
            media_type="video/mp4",
            filename=f"{Path(file_path).stem}.mp4"
        )
    
    logger.info(f"Transcoding to: {cached_mp4}")
    
    # Transcode synchronously
    success = transcode_to_mp4(str(requested_path), str(cached_mp4))
    
    if not success:
        if cached_mp4.exists():
            cached_mp4.unlink()
        raise HTTPException(
            status_code=500,
            detail="Transcoding failed"
        )
    
    # Return transcoded file
    return FileResponse(
        cached_mp4,
        media_type="video/mp4",
        filename=f"{Path(file_path).stem}.mp4"
    )

@app.post("/torrent/{torrent_hash}/upload-to-r2")
async def upload_to_r2(torrent_hash: str, file_path: Optional[str] = None):
    """Upload files to R2"""
    if not R2_ENABLED or not r2_client:
        raise HTTPException(status_code=400, detail="R2 not enabled")
    
    torrents = await qb_request("GET", "/torrents/info", {"hashes": torrent_hash})
    if not torrents or len(torrents) == 0:
        raise HTTPException(status_code=404, detail="Torrent not found")
    
    t = torrents[0]
    base_dir = Path(t.get("save_path", "")).resolve()
    uploaded = []
    
    try:
        if file_path:
            requested_path = (base_dir / file_path).resolve()
            if not str(requested_path).startswith(str(base_dir)):
                raise HTTPException(status_code=403, detail="Access denied")
            
            if requested_path.exists() and requested_path.is_file():
                with open(requested_path, 'rb') as f:
                    r2_key = f"{torrent_hash}/{file_path}"
                    r2_client.upload_fileobj(f, R2_BUCKET, r2_key)
                    uploaded.append(file_path)
        else:
            for root, dirs, files_list in os.walk(base_dir):
                for fname in files_list:
                    fpath = Path(root) / fname
                    relative_path = fpath.relative_to(base_dir)
                    r2_key = f"{torrent_hash}/{relative_path}"
                    
                    with open(fpath, 'rb') as f:
                        r2_client.upload_fileobj(f, R2_BUCKET, r2_key)
                        uploaded.append(str(relative_path))
        
        return {
            "status": "uploaded",
            "files": uploaded,
            "bucket": R2_BUCKET,
            "count": len(uploaded)
        }
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/torrent/{torrent_hash}/r2/{file_path:path}")
async def delete_from_r2(torrent_hash: str, file_path: str):
    """Delete file from R2"""
    if not R2_ENABLED or not r2_client:
        raise HTTPException(status_code=400, detail="R2 not enabled")
    
    try:
        r2_key = f"{torrent_hash}/{file_path}"
        r2_client.delete_object(Bucket=R2_BUCKET, Key=r2_key)
        return {"status": "deleted", "key": r2_key}
    except Exception as e:
        logger.error(f"Delete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/torrents")
async def list_torrents():
    """List all torrents"""
    torrents = await qb_request("GET", "/torrents/info")
    
    if torrents is None:
        raise HTTPException(status_code=503, detail="qBittorrent not connected")
    
    return [
        {
            "hash": t.get("hash"),
            "name": t.get("name"),
            "state": t.get("state"),
            "progress": t.get("progress"),
            "download_speed": t.get("dl_speed"),
            "peers": t.get("peers_total")
        }
        for t in torrents
    ]

@app.delete("/torrent/{torrent_hash}")
async def remove_torrent(torrent_hash: str, delete_files: bool = False):
    """Remove a torrent"""
    data = {
        "hashes": torrent_hash,
        "deleteFiles": "true" if delete_files else "false"
    }
    
    result = await qb_request("POST", "/torrents/delete", data)
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to remove torrent")
    
    return {"status": "removed"}

@app.post("/torrent/{torrent_hash}/pause")
async def pause_torrent(torrent_hash: str):
    """Pause a torrent"""
    data = {"hashes": torrent_hash}
    
    result = await qb_request("POST", "/torrents/pause", data)
    if result is not None:
        return {"status": "paused"}
    
    result = await qb_request("POST", "/torrents/stop", data)
    if result is not None:
        return {"status": "paused"}
    
    raise HTTPException(status_code=500, detail="Failed to pause")

@app.post("/torrent/{torrent_hash}/resume")
async def resume_torrent(torrent_hash: str):
    """Resume a torrent"""
    data = {"hashes": torrent_hash}
    
    result = await qb_request("POST", "/torrents/resume", data)
    if result is not None:
        return {"status": "resumed"}
    
    result = await qb_request("POST", "/torrents/start", data)
    if result is not None:
        return {"status": "resumed"}
    
    raise HTTPException(status_code=500, detail="Failed to resume")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)