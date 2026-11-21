# diagnostic.py
import asyncio
import libtorrent as lt
from torrent.manager import TorrentManager
from torrent.session import TorrentSession
import time

INFO_HASH = r"2fa7c09b7526b28c44196ed0cc7e00ad6f90dcca&dn=Torrentio%0A1080p&tr=tracker%3Audp%3A%2F%2Fopentor.net%3A6969&tr=tracker%3Ahttp%3A%2F%2Fretracker.local%2Fannounce&tr=2fa7c09b7526b28c44196ed0cc7e00ad6f90dcca&tr=tracker%3Audp%3A%2F%2Fzer0day.ch%3A1337%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.publictracker.xyz%3A6969%2Fannounce&tr=tracker%3Ahttp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=tracker%3Audp%3A%2F%2Fopen.demonii.com%3A1337%2Fannounce&tr=tracker%3Audp%3A%2F%2Fopen.tracker.cl%3A1337%2Fannounce&tr=tracker%3Audp%3A%2F%2Fopen.stealth.si%3A80%2Fannounce&tr=tracker%3Audp%3A%2F%2Fexodus.desync.com%3A6969%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.wildkat.net%3A6969%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.torrent.eu.org%3A451%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.qu.ax%3A6969%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.opentorrent.top%3A6969%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.gmi.gd%3A6969%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.ducks.party%3A1984%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.dler.org%3A6969%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.corpscorp.online%3A80%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.bittor.pw%3A1337%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.auctor.tv%3A6969%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker-udp.gbitt.info%3A80%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftorrentclub.online%3A54123%2Fannounce&tr=tracker%3Audp%3A%2F%2Fseedpeer.net%3A6969%2Fannounce&tr=tracker%3Ahttp%3A%2F%2Fbt.t-ru.org%2Fann%3Fmagnet&tr=tracker%3Ahttp%3A%2F%2Fbt2.t-ru.org%2Fann%3Fmagnet&tr=tracker%3Ahttp%3A%2F%2Fbt3.t-ru.org%2Fann%3Fmagnet&tr=tracker%3Ahttp%3A%2F%2Fbt4.t-ru.org%2Fann%3Fmagnet"  # replace with your failing info_hash
SAVE_PATH = "./downloads"  # same as your run

async def run():
    ts = TorrentSession()
    await ts.start()
    mgr = TorrentManager(ts)
    # If the magnet is already added in your app, you can get the handle from manager.torrents
    handle = mgr.get_handle(INFO_HASH)
    if not handle:
        print("Handle not found in manager.torrents. If torrent is added by another process, adapt script.")
        return

    ti = None
    try:
        ti = handle.get_torrent_info()
    except Exception:
        print("No metadata available yet.")
    if ti:
        print("Torrent name:", ti.name())
        print("num_pieces:", ti.num_pieces())
        print("piece_length:", ti.piece_length())

    status = handle.status()
    print("handle.status() summary:")
    print("  has_metadata:", status.has_metadata)
    print("  progress:", status.progress)
    print("  num_peers:", status.num_peers)
    print("  download_rate (B/s):", status.download_rate)
    print("  download_payload_rate (B/s):", getattr(status, "download_payload_rate", None))
    print("  num_seeds:", getattr(status, "num_seeds", None))

    # show first N pieces availability locally
    N = 24
    print("\nLocal have_piece for first pieces:")
    for i in range(0, min(N, ti.num_pieces() if ti else N)):
        try:
            have = handle.have_piece(i)
        except Exception:
            have = None
        print(f"  piece {i}: have={have}")

    # show piece availability (global) if available
    try:
        pa = handle.status().piece_availability  # sometimes present
        if pa is not None:
            print("\npiece availability array (first 50):", pa[:50])
    except Exception:
        pass

    # print connected peers info (basic)
    print("\nConnected peers (peer_info):")
    try:
        peers = handle.get_peer_info()
        for p in peers:
            print(f"  {p.ip} - flags={p.flags} - up={p.upload_rate/1024:.1f}KB/s down={p.download_rate/1024:.1f}KB/s")
    except Exception as e:
        print("  unable to get peers via handle.get_peer_info():", e)

    # optional: force reannounce to trackers
    print("\nForcing tracker reannounce (will return quickly):")
    try:
        handle.force_reannounce()
        print("  force_reannounce() called")
    except Exception as e:
        print("  force_reannounce failed:", e)

    # sleep a short while and reprint summary
    print("\nSleeping 5s then re-checking status...")
    await asyncio.sleep(5)
    status = handle.status()
    print("  after sleep: num_peers=", status.num_peers, "download_rate=", status.download_rate, "progress=", status.progress)
    for i in range(0, min(12, ti.num_pieces() if ti else 12)):
        print(f"   piece {i} have={handle.have_piece(i)}")

if __name__ == "__main__":
    asyncio.run(run())