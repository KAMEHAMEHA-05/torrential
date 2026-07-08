import asyncio
import libtorrent as lt
from pathlib import Path

SESSION_DIR = Path("./session")

STATE_FILE = (
    SESSION_DIR / "session_state.json"
)

RESUME_DIR = (
    SESSION_DIR / "resume"
)

SESSION_DIR.mkdir(
    parents=True,
    exist_ok=True
)

RESUME_DIR.mkdir(
    parents=True,
    exist_ok=True
)



class TorrentSession:

    def __init__(self):

        settings = {

            #
            # NETWORK
            #

            "listen_interfaces":
                "0.0.0.0:6881",

            "enable_dht": True,
            "enable_lsd": True,
            "enable_upnp": True,
            "enable_natpmp": True,

            #
            # CONNECTIONS
            #

            "connections_limit": 1000,

            "active_downloads": 100,
            "active_seeds": 50,

            "unchoke_slots_limit": 50,

            #
            # REQUEST PIPELINING
            #

            "max_out_request_queue": 10000,

            "whole_pieces_threshold": 30,

            "request_timeout": 10,
            "peer_timeout": 20,

            #
            # DISK / CACHE
            #

            "aio_threads": 32,

            "cache_size": 8192,

            "cache_expiry": 300,

            #
            # STREAMING
            #

            "strict_end_game_mode": False,

            "use_read_cache": True,

            "coalesce_reads": False,
            "coalesce_writes": False,

            #
            # ALERTS
            #

            "alert_mask":
                lt.alert.category_t.all_categories,
            
            "seed_choking_algorithm": 0,
            "choking_algorithm": 0

        }

        self.session = lt.session(settings)

        if STATE_FILE.exists():

            try:

                with open(STATE_FILE, "r") as f:

                    with open(
                        STATE_FILE,
                        "rb"
                    ) as f:

                        state = lt.bdecode(
                            f.read()
                        )

                    self.session.load_state(
                        state
                    )

                self.session.load_state(
                    state
                )

                print("Restored session state")

            except Exception as e:

                print("Failed restoring state:", e)

        self.session.start_dht()

        self.running = False


    async def start(self):

        self.running = True

        asyncio.create_task(
            self.alert_loop()
        )

        asyncio.create_task(
            self.state_loop()
        )

        asyncio.create_task(
            self.resume_loop()
        )

    IMPORTANT_ALERTS = (

        lt.metadata_received_alert,

        lt.torrent_finished_alert,

        lt.file_completed_alert,

        lt.torrent_error_alert,

        lt.peer_error_alert
    )


    async def alert_loop(self):

        while self.running:

            alerts = self.session.pop_alerts()

            for alert in alerts:

                if isinstance(
                    alert,
                    self.IMPORTANT_ALERTS
                ):

                    print(alert)

            await asyncio.sleep(0.1)

    def save_state(self):

        try:

            state = lt.bencode(

                self.session.save_state()
            )

            with open(
                STATE_FILE,
                "wb"
            ) as f:

                f.write(state)

            print(
                "Saved session state"
            )

        except Exception as e:

            print(
                "Failed saving state:",
                e
            )

    async def state_loop(self):

        while self.running:

            self.save_state()

            await asyncio.sleep(60)

    async def resume_loop(self):

        while self.running:

            #
            # request resume data
            #

            for handle in self.session.get_torrents():

                if not handle.is_valid():
                    continue

                try:

                    handle.save_resume_data()

                except:
                    pass

            #
            # process alerts
            #

            alerts = (
                self.session.pop_alerts()
            )

            for alert in alerts:

                if isinstance(
                    alert,
                    lt.save_resume_data_alert
                ):

                    data = (
                        lt.write_resume_data_buf(
                            alert.params
                        )
                    )

                    info_hash = str(
                        alert.handle.info_hash()
                    )

                    path = (
                        RESUME_DIR
                        /
                        f"{info_hash}.fastresume"
                    )

                    with open(
                        path,
                        "wb"
                    ) as f:

                        f.write(data)

            await asyncio.sleep(30)

    async def stop(self):

        self.running = False

        self.save_state()

        print(
            "Torrent session stopped"
        )