import time
import threading
import logging

from . import NFP

log = logging.getLogger(__name__)


class KeepAliver:
    """
    Helper class to run keepalives between Broker and Workers in a consistent way.

    Args:
        address (str): Optional address to send keepalives to.
        socket: ZeroMQ socket to use to send keepalives to.
        multiplier (int): Number of keepalives before considered dead.
        keepalive (int): Interval between keepalives in milliseconds.
        exit_event (threading.Event): Global exit event signaled by NFAPI if set, stop sending keepalives.
        service (str): Name of the service to include in keepalives.
        whoami (str): Identifier e.g. NFP.WORKER or NFP.BROKER to use as keepalives header.
        name (str): Descriptive name to include in logs.
        socket_lock: Lock to synchronize access to the socket.

    Attributes:
        address (str): Address to send keepalives to.
        socket: ZeroMQ socket to use to send keepalives to.
        exit_event (threading.Event): Global exit event.
        destroy_event (threading.Event): Event used by worker to stop keepalives.
        keepalive (int): Interval between keepalives in milliseconds.
        multiplier (int): Number of keepalives before considered dead.
        service (str): Name of the service to include in keepalives.
        whoami (str): Identifier to use as keepalives header.
        name (str): Descriptive name to include in logs.
        socket_lock: Lock to synchronize access to the socket.
        started_at (float): Timestamp when keepalives started.
        keepalives_received (int): Number of keepalives received.
        keepalives_send (int): Number of keepalives sent.
        holdtime (float): Expiry time unless heartbeat is received.
        keepalive_at (float): Time to send the next keepalive.
        keepalive_thread (threading.Thread): Thread to run keepalives.

    Methods:
        start(): Start keepalives thread.
        stop(): Stop keepalives thread.
        run(): Send heartbeats at keepalive interval.
        received_heartbeat(msg): Update holdtime when a heartbeat is received.
        restart(socket): Restart keepalives with a new socket.
        is_alive(): Check if the other party is seen before expiry.
        show_holdtime(): Show remaining holdtime.
        show_alive_for(): Show duration since keepalives started.
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
        self.destroy_event = (
            threading.Event()
        )  # destroy event, used by worker to stop keepalives
        self.keepalive = keepalive
        self.multiplier = multiplier
        self.service = service
        self.whoami = whoami
        self.name = f"{name}-keepaliver"
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
        """
        Start the keepalives thread and record the start time.

        This method initiates the keepalive thread and sets the `started_at`
        attribute to the current time.

        Returns:
            bool: True if the keepalive thread was successfully started.
        """
        self.keepalive_thread.start()
        self.started_at = time.time()
        return True

    def stop(self):
        """
        Stops the keepalive thread by setting the destroy event and joining the thread.

        This method first checks if the destroy event is not already set. If it is not set,
        it sets the destroy event to signal the keepalive thread to stop. Then, it waits
        for the keepalive thread to finish execution by calling join() on it.

        Returns:
            bool: True if the keepalive thread was successfully stopped.
        """
        if not self.destroy_event.is_set():
            self.destroy_event.set()
        self.keepalive_thread.join()
        return True

    def run(self):
        """
        Continuously send heartbeat messages at the specified keepalive interval.

        This method runs in a loop until either the `exit_event` or `destroy_event` is set.
        It sends a heartbeat message if the current time exceeds the `keepalive_at` timestamp.
        The message format depends on whether the `address` is specified.

        The method also handles exceptions that may occur during the sending of the message
        and logs the error. After sending a heartbeat, it updates the `keepalive_at` timestamp
        and increments the `keepalives_send` counter. The loop sleeps for 0.1 seconds between
        iterations.

        Raises:
            Exception: If an error occurs while sending the heartbeat message.
        """
        while not self.exit_event.is_set() and not self.destroy_event.is_set():
            if time.time() > self.keepalive_at:  # time to send heartbeat
                if self.address:
                    msg = [self.address, b"", self.whoami, NFP.KEEPALIVE, self.service]
                else:
                    msg = [b"", self.whoami, NFP.KEEPALIVE, self.service]
                with self.socket_lock:
                    try:
                        self.socket.send_multipart(msg)
                    except Exception as e:
                        log.error(
                            f"{self.name} - failed to send keepalive, error '{e}'"
                        )
                self.keepalive_at = time.time() + 0.001 * self.keepalive
                self.keepalives_send += 1
                log.debug(f"{self.name} - send keepalive '{msg}'")
            time.sleep(0.1)

    def received_heartbeat(self, msg):
        """
        Handles the reception of a heartbeat message from another party.

        This method updates the holdtime and increments the count of received keepalives.

        Args:
            msg (str): The heartbeat message received.
        """
        log.debug(f"{self.name} - received keepalive '{msg}'")
        self.keepalives_received += 1
        self.holdtime = time.time() + 0.001 * self.multiplier * self.keepalive

    def restart(self, socket):
        """
        Restart keepalives with a new socket.

        This method reinitializes the keepalive mechanism with a new socket. It resets
        the counters for received and sent keepalives, sets the start time to the current
        time, and calculates the holdtime and the next keepalive time based on the
        provided keepalive interval and multiplier.

        Args:
            socket: The new socket to be used for keepalives.
        """
        self.socket = socket
        self.keepalives_received = 0
        self.keepalives_send = 0
        self.started_at = time.time()
        self.holdtime = (
            time.time() + 0.001 * self.multiplier * self.keepalive
        )  # expires at this point, unless heartbeat
        self.keepalive_at = (
            time.time() + 0.001 * self.keepalive
        )  # when to send keepalive

    def is_alive(self):
        """
        Check if the other party is still alive based on the hold time.

        Returns:
            bool: True if the other party has been seen before the hold time expires, False otherwise.
        """
        return self.holdtime > time.time()

    def show_holdtime(self):
        """
        Calculate and return the remaining hold time.

        This method subtracts the current time from the holdtime attribute
        and rounds the result to one decimal place.

        Returns:
            float: The remaining hold time in seconds, rounded to one decimal place.
        """
        return round(self.holdtime - time.time(), 1)

    def show_alive_for(self):
        """
        Calculate the duration for which the instance has been alive.

        Returns:
            int: The number of seconds since the instance was started.
        """
        return int(time.time() - self.started_at)
