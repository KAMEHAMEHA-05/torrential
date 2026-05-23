from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
import qbittorrentapi
import os
import logging
from pathlib import Path
from typing import Optional
import aiofiles
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

QB_HOST = os.getenv("QB_HOST", "localhost")
QB_PORT = int(os.getenv("QB_PORT", "8080"))
QB_USERNAME = os.getenv("QB_USERNAME", "admin")
QB_PASSWORD = os.getenv("QB_PASSWORD", "adminadmin")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/downloads")

qb_client = None

class TorrentRequest(BaseModel):
    magnet: str
    save_path: Optional[str] = None

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

@app.on_event("startup")
async def startup():
    global qb_client
    try:
        qb_client = qbittorrentapi.Client(
            host=QB_HOST,
            port=QB_PORT,
            username=QB_USERNAME,
            password=QB_PASSWORD
        )
        qb_client.auth_log_in()
        logger.info("Connected to qBittorrent")
    except Exception as e:
        logger.error(f"Failed to connect to qBittorrent: {e}")
        qb_client = None

@app.get("/health")
async def health():
    if qb_client:
        try:
            qb_client.app.version
            return {"status": "ok", "client": "qbittorrent"}
        except:
            return {"status": "error", "client": "qbittorrent"}
    return {"status": "error", "client": "none"}

@app.post("/torrent/add")
async def add_torrent(req: TorrentRequest):
    if not qb_client:
        raise HTTPException(status_code=503, detail="qBittorrent not connected")
    
    try:
        save_path = req.save_path or DOWNLOAD_DIR
        qb_client.torrents_add(
            urls=req.magnet,
            save_path=save_path,
            is_paused=False
        )
        
        # Wait a moment for torrent to be added
        time.sleep(1)
        
        torrents = qb_client.torrents_info()
        if torrents:
            t = torrents[-1]  # Get the last added torrent
            return {
                "hash": t.hash,
                "name": t.name,
                "status": "added"
            }
        
        raise HTTPException(status_code=500, detail="Failed to add torrent")
    except Exception as e:
        logger.error(f"Error adding torrent: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/torrent/{torrent_hash}/status")
async def get_torrent_status(torrent_hash: str):
    if not qb_client:
        raise HTTPException(status_code=503, detail="qBittorrent not connected")
    
    try:
        torrent = qb_client.torrents_info(torrent_hashes=torrent_hash)
        if not torrent:
            raise HTTPException(status_code=404, detail="Torrent not found")
        
        t = torrent[0]
        return TorrentStatus(
            name=t.name,
            state=t.state,
            progress=t.progress,
            total_size=t.total_size,
            downloaded=t.downloaded,
            download_speed=t.dl_speed,
            upload_speed=t.up_speed,
            peers=t.peers_total,
            seeds=t.seeds_total,
            eta=t.eta
        )
    except Exception as e:
        logger.error(f"Error getting torrent status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/torrent/{torrent_hash}/files")
async def get_torrent_files(torrent_hash: str):
    if not qb_client:
        raise HTTPException(status_code=503, detail="qBittorrent not connected")
    
    try:
        files = qb_client.torrents_files(torrent_hashes=torrent_hash)
        if not files:
            raise HTTPException(status_code=404, detail="Torrent not found")
        
        return [
            {
                "name": f.name,
                "size": f.size,
                "progress": f.progress,
                "path": f.name
            }
            for f in files[0]
        ]
    except Exception as e:
        logger.error(f"Error getting torrent files: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/torrent/{torrent_hash}/file/{file_path:path}")
async def stream_file(torrent_hash: str, file_path: str):
    if not qb_client:
        raise HTTPException(status_code=503, detail="qBittorrent not connected")
    
    try:
        torrent = qb_client.torrents_info(torrent_hashes=torrent_hash)
        if not torrent:
            raise HTTPException(status_code=404, detail="Torrent not found")
        
        t = torrent[0]
        full_path = Path(t.save_path) / file_path
        
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        return FileResponse(
            full_path,
            media_type="application/octet-stream",
            filename=full_path.name
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/torrents")
async def list_torrents():
    if not qb_client:
        raise HTTPException(status_code=503, detail="qBittorrent not connected")
    
    try:
        torrents = qb_client.torrents_info()
        return [
            {
                "hash": t.hash,
                "name": t.name,
                "state": t.state,
                "progress": t.progress,
                "download_speed": t.dl_speed,
                "peers": t.peers_total
            }
            for t in torrents
        ]
    except Exception as e:
        logger.error(f"Error listing torrents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/torrent/{torrent_hash}")
async def remove_torrent(torrent_hash: str, delete_files: bool = False):
    if not qb_client:
        raise HTTPException(status_code=503, detail="qBittorrent not connected")
    
    try:
        qb_client.torrents_delete(
            delete_files=delete_files,
            torrent_hashes=torrent_hash
        )
        return {"status": "removed"}
    except Exception as e:
        logger.error(f"Error removing torrent: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/torrent/{torrent_hash}/pause")
async def pause_torrent(torrent_hash: str):
    if not qb_client:
        raise HTTPException(status_code=503, detail="qBittorrent not connected")
    
    try:
        qb_client.torrents_pause(torrent_hashes=torrent_hash)
        return {"status": "paused"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/torrent/{torrent_hash}/resume")
async def resume_torrent(torrent_hash: str):
    if not qb_client:
        raise HTTPException(status_code=503, detail="qBittorrent not connected")
    
    try:
        qb_client.torrents_resume(torrent_hashes=torrent_hash)
        return {"status": "resumed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
