import asyncio
import libtorrent as lt


class TorrentSession:

    def __init__(self):

        settings = {

            "enable_dht": True,

            "enable_lsd": True,

            "enable_upnp": True,

            "enable_natpmp": True,

            "listen_interfaces":
                "0.0.0.0:6881",

            "connections_limit": 500,

            "active_downloads": 50,

            "active_seeds": 50,

            "aio_threads": 8,

            "cache_size": 2048,

            "alert_mask":
                lt.alert.category_t.all_categories
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