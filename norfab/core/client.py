"""Majordomo Protocol Client API, Python version.

Implements the MDP/Worker spec at http:#rfc.zeromq.org/spec:7.

Author: Min RK <benjaminrk@gmail.com>
Based on Java example by Arkadiusz Orzechowski
"""

import logging
import zmq

from . import MDP
from .zhelpers import dump

# logging.basicConfig(
#     format="%(asctime)s.%(msecs)d [%(name)s:%(lineno)d %(levelname)s] -- %(message)s",
#     datefmt="%Y-%m-%d %H:%M:%S",
#     level=logging.DEBUG,
# )

log = logging.getLogger(__name__)


class MajorDomoClient(object):
    """Majordomo Protocol Client API, Python version.

    Implements the MDP/Worker spec at http:#rfc.zeromq.org/spec:7.
    """

    broker = None
    ctx = None
    client = None
    poller = None
    timeout = 2500
    retries = 3

    def __init__(self, broker):
        self.broker = broker
        self.ctx = zmq.Context()
        self.poller = zmq.Poller()
        self.reconnect_to_broker()

    def reconnect_to_broker(self):
        """Connect or reconnect to broker"""
        if self.client:
            self.poller.unregister(self.client)
            self.client.close()
        self.client = self.ctx.socket(zmq.REQ)
        self.client.linger = 0
        self.client.connect(self.broker)
        self.poller.register(self.client, zmq.POLLIN)
        log.debug(f"connected to broker at '{self.broker}'")

    def send(self, service, request):
        """Send request to broker and get reply by hook or crook.

        Takes ownership of request message and destroys it when sent.
        Returns the reply message or None if there was no reply.
        """
        if not isinstance(request, list):
            request = [request]
        request = [MDP.C_CLIENT, service] + request
        log.debug(f"sending request to '{service}' service: {request} ")

        reply = None

        retries = self.retries
        while retries > 0:
            self.client.send_multipart(request)
            try:
                items = self.poller.poll(self.timeout)
            except KeyboardInterrupt:
                break  # interrupted

            if items:
                msg = self.client.recv_multipart()
                log.debug(f"received reply: {msg}")

                # Don't try to handle errors, just assert noisily
                assert len(msg) >= 3

                header = msg.pop(0)
                assert MDP.C_CLIENT == header

                reply_service = msg.pop(0)
                assert service == reply_service

                reply = msg
                break
            else:
                if retries:
                    log.warning(f"Client no reply from broker at '{self.broker}', reconnecting")
                    self.reconnect_to_broker()
                else:
                    log.error(f"Client permanent broker connection error, abandoning '{self.broker}'")
                    break
                retries -= 1

        return reply

    def destroy(self):
        self.ctx.destroy()
