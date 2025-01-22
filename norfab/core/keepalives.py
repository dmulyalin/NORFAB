import time
import threading
import logging

from . import NFP

log = logging.getLogger(__name__)


class KeepAliver:
    """
    Helper class to run keepalives between Broker and Workers in consistent way.

    :param address: string, optional address to send keepalives to
    :param socket: ZeroMQ socket to use to send keepalives to
    :param multiplier: int, number of keepalives before dead
    :param keepalive: int, interval between keepalives in milliseconds
    :param exit_event: threading Event, if set, stop sending keepalives
    :param service: string, name of the service to include in keepalives
    :param whoami: string, who am I e.g. NFP.WORKER or NFP.BROKER to use as keepalives header
    :param name: descriptive name to include in logs
    """

    def __init__(
        self,
        address: str,
        socket,
        multiplier: int,  # e.g. 6 times
        keepalive: int,  # e.g. 5000 ms
        exit_event: threading.Event,
        service: str,
        whoami: str,  # NFP.BROKER or NFP.WORKER
        name: str,
        socket_lock,
    ):
        self.address = address
        self.socket = socket
        self.exit_event = exit_event or threading.Event()
        self.keepalive = keepalive
        self.multiplier = multiplier
        self.service = service
        self.whoami = whoami
        self.name = name
        self.socket_lock = socket_lock

        self.started_at = 0
        self.keepalives_received = 0
        self.keepalives_send = 0
        self.holdtime = (
            time.time() + 0.001 * self.multiplier * self.keepalive
        )  # expires at this point, unless heartbeat
        self.keepalive_at = (
            time.time() + 0.001 * self.keepalive
        )  # when to send keepalive

        self.keepalive_thread = threading.Thread(
            target=self.run, name=f"{self.name}_keepalives_thread", daemon=True
        )

    def start(self):
        """Start keepalives thread."""
        self.keepalive_thread.start()
        self.started_at = time.time()
        return True

    def stop(self):
        if not self.exit_event.is_set():
            self.exit_event.set()
        self.keepalive_thread.join()
        return True

    def run(self):
        """Send heartbeats to at keepalive interval."""
        while not self.exit_event.is_set():
            if time.time() > self.keepalive_at:  # time to send heartbeat
                if self.address:
                    msg = [self.address, b"", self.whoami, NFP.KEEPALIVE, self.service]
                else:
                    msg = [b"", self.whoami, NFP.KEEPALIVE, self.service]
                with self.socket_lock:
                    try:
                        self.socket.send_multipart(msg)
                    except Exception as e:
                        msg = f"{self.name} - failed to send keepalive, trigerring exit event, error '{e}'"
                        log.error(msg)
                        self.exit_event.set()
                        break
                self.keepalive_at = time.time() + 0.001 * self.keepalive
                self.keepalives_send += 1
                log.debug(f"{self.name} - send keepalive '{msg}'")
            time.sleep(0.1)

    def received_heartbeat(self, msg):
        """Received heartbeat from other party, update holdtime time."""
        log.debug(f"{self.name} - received keepalive '{msg}'")
        self.keepalives_received += 1
        self.holdtime = time.time() + 0.001 * self.multiplier * self.keepalive

    def is_alive(self):
        """True if other party seen before expiry False otherwise."""
        return self.holdtime > time.time()

    def show_holdtime(self):
        return round(self.holdtime - time.time(), 1)

    def show_alive_for(self):
        return int(time.time() - self.started_at)
