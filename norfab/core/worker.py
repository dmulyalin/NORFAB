"""Majordomo Protocol Worker API, Python version

Implements the MDP/Worker spec at http:#rfc.zeromq.org/spec:7.

Author: Min RK <benjaminrk@gmail.com>
Based on Java example by Arkadiusz Orzechowski
"""

import logging
import time
import zmq
import json
import traceback

from .zhelpers import dump
from . import MDP

# logging.basicConfig(
#     format="%(asctime)s.%(msecs)d [%(name)s:%(lineno)d %(levelname)s] -- %(message)s",
#     datefmt="%Y-%m-%d %H:%M:%S",
#     level=logging.DEBUG,
# )

log = logging.getLogger(__name__)


class MajorDomoWorker(object):
    """Majordomo Protocol Worker API, Python version

    Implements the MDP/Worker spec at http:#rfc.zeromq.org/spec:7.
    """

    HEARTBEAT_LIVENESS = 3  # 3-5 is reasonable
    broker = None
    ctx = None
    service = None

    worker = None  # Socket to broker
    heartbeat_at = 0  # When to send HEARTBEAT (relative to time.time(), so in seconds)
    liveness = 0  # How many attempts left
    heartbeat = 2500  # Heartbeat delay, msecs
    reconnect = 2500  # Reconnect delay, msecs

    # Internal state
    expect_reply = False  # False only at start

    timeout = 2500  # poller timeout

    # Return address, if any
    reply_to = None

    def __init__(self, broker, service, name, exit_event=None):
        self.broker = broker
        self.service = service
        self.name = name
        self.ctx = zmq.Context()
        self.poller = zmq.Poller()
        self.reconnect_to_broker()
        self.exit_event = exit_event

    def reconnect_to_broker(self):
        """Connect or reconnect to broker"""
        if self.worker:
            self.poller.unregister(self.worker)
            self.worker.close()
        self.worker = self.ctx.socket(zmq.DEALER)
        self.worker.setsockopt_unicode(zmq.IDENTITY, self.name, "utf8")
        self.worker.linger = 0
        self.worker.connect(self.broker)
        self.poller.register(self.worker, zmq.POLLIN)

        # Register service with broker
        self.send_to_broker(MDP.W_READY, self.service, [])

        # If liveness hits zero, queue is considered disconnected
        self.liveness = self.HEARTBEAT_LIVENESS
        self.heartbeat_at = time.time() + 1e-3 * self.heartbeat

        log.info(f"{self.name} - connected to broker at '{self.broker}'")

    def send_to_broker(self, command, option=None, msg=None):
        """Send message to broker.

        If no msg is provided, creates one internally
        """
        if msg is None:
            msg = []
        elif not isinstance(msg, list):
            msg = [msg]

        if option:
            msg = [option] + msg

        msg = [b"", MDP.W_WORKER, command] + msg
        log.debug(f"{self.name} - sending '{command}' to broker: {msg}")

        self.worker.send_multipart(msg)

    def recv(self, reply=None):
        """Send reply, if any, to broker and wait for next request."""
        # Format and send the reply if we were provided one
        assert reply is not None or not self.expect_reply

        if reply is not None:
            assert self.reply_to is not None
            reply = [self.reply_to, b""] + reply
            self.send_to_broker(MDP.W_REPLY, msg=reply)

        self.expect_reply = True

        while True:
            # Poll socket for a reply, with timeout
            try:
                items = self.poller.poll(self.timeout)
            except KeyboardInterrupt:
                break  # Interrupted

            if items:
                msg = self.worker.recv_multipart()
                log.debug(f"{self.name} - received message from broker: {msg}")

                self.liveness = self.HEARTBEAT_LIVENESS
                # Don't try to handle errors, just assert noisily
                assert len(msg) >= 3

                empty = msg.pop(0)
                assert empty == b""

                header = msg.pop(0)
                assert header == MDP.W_WORKER

                command = msg.pop(0)
                if command == MDP.W_REQUEST:
                    # We should pop and save as many addresses as there are
                    # up to a null part, but for now, just save one...
                    self.reply_to = msg.pop(0)
                    # pop empty
                    empty = msg.pop(0)
                    assert empty == b""

                    return msg  # We have a request to process
                elif command == MDP.W_HEARTBEAT:
                    # Do nothing for heartbeats
                    pass
                elif command == MDP.W_DISCONNECT:
                    self.reconnect_to_broker()
                elif command == MDP.W_INVENTORY_REPLY:
                    assert len(msg) == 1
                    self.expect_reply = (
                        False  # reset back to False to re-init while loop
                    )
                    return msg.pop(0)
                else:
                    log.error(f"{self.name} - invalid input message: {msg}")

            else:
                self.liveness -= 1
                if self.liveness == 0:
                    log.warning(
                        f"{self.name} - disconnected from broker '{self.broker}' - retrying"
                    )
                    try:
                        time.sleep(1e-3 * self.reconnect)
                    except KeyboardInterrupt:
                        break
                    self.reconnect_to_broker()

            # Send HEARTBEAT if it's time
            if time.time() > self.heartbeat_at:
                self.send_to_broker(MDP.W_HEARTBEAT)
                self.heartbeat_at = time.time() + 1e-3 * self.heartbeat

            # check if need to stop
            if self.exit_event is not None and self.exit_event.is_set():
                self.destroy()
                break

        log.info(f"interrupt received, killing worker {self.name} ")
        return None

    def load_inventory(self):
        """
        Function to load inventory from broker for this worker name.
        """
        log.debug(
            f"{self.name} - sending 'MDP.W_INVENTORY' to broker requesting inventory data"
        )
        self.send_to_broker(
            MDP.W_INVENTORY_REQUEST, option=self.name.encode(encoding="utf-8")
        )
        log.debug(
            f"Worker '{self.name}' received inventory data from broker at '{self.broker}'"
        )

        return json.loads(self.recv())

    def destroy(self):
        # context.destroy depends on pyzmq >= 2.1.10
        self.ctx.destroy(0)

    def work(self):
        """
        Main worker loop to receive tasks and return results
        """
        reply = None
        while True:
            request = self.recv(reply)
            if request is None:
                break  # Worker was interrupted

            data = json.loads(request[0])
            task = data.pop("task")
            args = data.pop("args", [])
            kwargs = data.pop("kwargs", {})

            log.debug(
                f"worker received task '{task}' from {self.reply_to}, data: {data}, args: '{args}', kwargs: '{kwargs}'"
            )

            try:
                if getattr(self, task, None):
                    if callable(getattr(self, task)):
                        reply = getattr(self, task)(*args, **kwargs)
                    else:
                        reply = f"Worker {self.name} '{task}' not a callable function"
                else:
                    reply = f"Worker {self.name} unsupported task: '{task}'"
            except:
                reply = f"Worker experienced error:\n{traceback.format_exc()}"
                log.exception("Worker experienced error:\n")

            # need to return reply as a list
            reply = [json.dumps(reply).encode("utf-8")]
