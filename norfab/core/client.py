"""
NorFab Majordomo Protocol - NMP

Modified Majordomo Protocol Client API, Python version.

Original MDP/Client spec
Location: http:#rfc.zeromq.org/spec:7.
Author: Min RK <benjaminrk@gmail.com>
Based on Java example by Arkadiusz Orzechowski

NorFab Majordomo Protocol Client
================================

A REQUEST command consists of a multipart message of 6 or more frames, formatted on the wire as follows:

Frame 0: Empty (zero bytes, invisible to REQ application)
Frame 1: “MDPC01” (six bytes, representing MDP/Client v0.1)
Frame 2: Service name (printable string)
Frame 3: Worker(s) name (printable string)
Frames 4+: Request body (opaque binary)

A REPLY command consists of a multipart message of 4 or more frames, formatted on the wire as follows:

Frame 0: Empty (zero bytes, invisible to REQ application)
Frame 1: “MDPC01” (six bytes, representing MDP/Client v0.1)
Frame 2: Service name (printable string)
Frame 3: Worker(s) name (printable string)
Frames 4+: Reply body (opaque binary)
"""

import logging
import zmq
import sys
import time

from . import MDP
from .zhelpers import dump

from typing import Union, List

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

    def send(self, service: str, request: Union[str, List[str]], workers: str = "any"):
        """Send request to broker and get reply by hook or crook.

        Takes ownership of request message and destroys it when sent.
        Returns the reply message or None if there was no reply.
        """
        if not isinstance(service, bytes):
            service = service.encode("utf-8")

        if not isinstance(workers, bytes):
            workers = workers.encode("utf-8")
            
        # convert request to list of byte strings
        if not isinstance(request, list):
            request = [request]

        for index, i in enumerate(request):
            if not isinstance(i, bytes):
                request[index] = str(i).encode("utf-8")

        request = [MDP.C_CLIENT, service, workers] + request

        log.debug(f"sending request to '{service}' service workers '{workers}': {request} ")

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
                    log.warning(
                        f"Client no reply from broker at '{self.broker}', reconnecting"
                    )
                    self.reconnect_to_broker()
                else:
                    log.error(
                        f"Client permanent broker connection error, abandoning '{self.broker}'"
                    )
                    break
                retries -= 1
        else:
            log.error(f"{self.retries} retries attempts exceeded, exiting")

        log.debug(f"received reply from '{service}' service: {reply}")

        return reply

    def destroy(self):
        log.info("interrupt received, killing client")
        self.ctx.destroy()


class TSPClient(object):
    """
    TSP (Titanic Service Protocol) client implements TSP
    protocol communicating with services.
    """

    def __init__(self, broker):
        self.client = MajorDomoClient(broker)

    def service_call(self, service, request):
        """Calls a TSP service

        Returns reponse if successful (status code 200 OK), else None
        """
        reply = self.client.send(service, request)
        if reply:
            status = reply.pop(0)
            if status == b"200":
                return reply
            elif status == b"400":
                log.error("E: client fatal error 400, aborting")
                sys.exit(1)
            elif status == b"500":
                log.error("E: server fatal error 500, aborting")
                sys.exit(1)
        else:
            sys.exit(0)
            #  Interrupted or failed

    def send(self, service, request, workers=None):

        # check if MMI request - request to broker management interface
        # send request directly
        if service.startswith("mmi."):
            return self.client.send(service, request)

        #  1. Submit to service.request
        reply = self.service_call(f"{service}.request", request)

        uuid = None

        if reply:
            uuid = reply.pop(0)
            log.debug(f"request UUID {uuid}")

        #  2. Wait until we get a reply
        while True:
            time.sleep(0.1)
            request = [uuid]
            reply = self.service_call(f"{service}.reply", request)

            if reply:
                #  3. Close request
                request = [uuid]
                close_reply = self.service_call(f"{service}.close", request)

                return reply
            else:
                time.sleep(1)  #  Try again in 4 seconds

    def destroy(self):
        self.client.destroy()
