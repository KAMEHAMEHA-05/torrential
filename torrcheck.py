import libtorrent as lt
import time

info_hash = "e384442fe9a0493960abe2ee32e473281afb9fed"
magnet = f"magnet:?xt=urn:btih:{info_hash}"

ses = lt.session()
ses.listen_on(6881, 6891)

params = {
    "save_path": "/tmp",
    "storage_mode": lt.storage_mode_t.storage_mode_sparse,
}

handle = lt.add_magnet_uri(ses, magnet, params)

print("Downloading metadata...")

while not handle.has_metadata():
    s = handle.status()
    print(
        f"Peers: {s.num_peers}, "
        f"DHT nodes: {s.num_complete + s.num_incomplete}"
    )
    time.sleep(1)

info = handle.get_torrent_info()

print("Name:", info.name())
print("Total size:", info.total_size())

for f in info.files():
    print(f.path, f.size)