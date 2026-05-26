import asyncio
import libtorrent as lt


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

        self.session.start_dht()

        self.running = False


    async def start(self):

        self.running = True

        asyncio.create_task(
            self.alert_loop()
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