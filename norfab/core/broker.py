"""
Majordomo Protocol broker
A minimal implementation of http:#rfc.zeromq.org/spec:7 and spec:8

Author: Min RK <benjaminrk@gmail.com>
Based on Java example by Arkadiusz Orzechowski
"""

import logging
import sys
import time
import json

from binascii import hexlify

import zmq

from . import MDP
from .zhelpers import dump
from .inventory import NorFabInventory

# logging.basicConfig(
#     format="%(asctime)s.%(msecs)d [%(name)s:%(lineno)d %(levelname)s] -- %(message)s",
#     datefmt="%Y-%m-%d %H:%M:%S",
#     level=logging.DEBUG,
# )

log = logging.getLogger(__name__)


class Service(object):
    """a single Service"""

    name = None  # Service name
    requests = None  # List of client requests
    waiting = None  # List of waiting workers
    
    def __init__(self, name):
        self.name = name
        self.requests = []
        self.waiting = []
        self.known = set()


class Worker(object):
    """a Worker, idle or active"""

    identity = None  # hex Identity of worker
    address = None  # Address to route to
    service = None  # Owning service, if known
    expiry = None  # expires at this point, unless heartbeat

    def __init__(self, identity, address, lifetime):
        self.identity = identity
        self.address = address
        self.expiry = time.time() + 1e-3 * lifetime


class MajorDomoBroker(object):
    """
    Majordomo Protocol broker
    A minimal implementation of http:#rfc.zeromq.org/spec:7 and spec:8
    """

    # We'd normally pull these from config data
    INTERNAL_SERVICE_PREFIX = b"mmi."
    HEARTBEAT_LIVENESS = 6  # 3-5 is reasonable
    HEARTBEAT_INTERVAL = 5000  # msecs
    HEARTBEAT_EXPIRY = HEARTBEAT_INTERVAL * HEARTBEAT_LIVENESS

    # ---------------------------------------------------------------------

    ctx = None  # Our context
    socket = None  # Socket for clients & workers
    poller = None  # our Poller

    heartbeat_at = None  # When to send HEARTBEAT
    services = None  # known services
    workers = None  # known workers
    waiting = None  # idle workers

    # ---------------------------------------------------------------------

    inventory = None  # NorFab inventory object

    def __init__(self, exit_event=None, inventory: NorFabInventory = None):
        """Initialize broker state."""
        self.services = {}
        self.workers = {}
        self.waiting = []
        self.heartbeat_at = time.time() + 1e-3 * self.HEARTBEAT_INTERVAL
        self.ctx = zmq.Context()
        self.socket = self.ctx.socket(zmq.ROUTER)
        self.socket.linger = 0
        self.poller = zmq.Poller()
        self.poller.register(self.socket, zmq.POLLIN)
        self.exit_event = exit_event
        self.inventory = inventory

    # ---------------------------------------------------------------------

    def mediate(self):
        """
        Main broker work happens here
        
        Client send mesages of this frame format:
        
        
        """
        while True:
            try:
                items = self.poller.poll(self.HEARTBEAT_INTERVAL)
            except KeyboardInterrupt:
                break  # Interrupted
            if items:
                msg = self.socket.recv_multipart()
                log.debug(f"received message: {msg}")

                sender = msg.pop(0)
                empty = msg.pop(0)
                assert empty == b""
                header = msg.pop(0)

                if MDP.C_CLIENT == header:
                    self.process_client(sender, msg)
                elif MDP.W_WORKER == header:
                    self.process_worker(sender, msg)
                else:
                    log.error("invalid message: {msg}")

            self.purge_workers()
            self.send_heartbeats()

            # check if need to stop
            if self.exit_event is not None and self.exit_event.is_set():
                self.destroy()
                break

    def destroy(self):
        """Disconnect all workers, destroy context."""
        log.info(f"interrupt received, killing broker")
        while self.workers:
            for w in self.workers.values():
                self.delete_worker(w, True)
                break  # deleted one worker
        self.ctx.destroy(0)

    def process_client(self, sender, msg):
        """Process a request coming from a client."""
        assert len(msg) >= 2  # Service name + body
        service = msg.pop(0)
        target_worker = msg.pop(0)
        # Set reply return address to client sender
        msg = [sender, b""] + msg
        if service.startswith(self.INTERNAL_SERVICE_PREFIX):
            self.service_internal(service, msg)
        else:
            self.dispatch(self.require_service(service), target_worker, msg)

    def process_worker(self, sender, msg):
        """Process message sent to us by a worker."""
        assert len(msg) >= 1  # At least, command

        command = msg.pop(0)

        worker_ready = hexlify(sender) in self.workers

        worker = self.require_worker(sender)

        if MDP.W_READY == command:
            assert len(msg) >= 1  # At least, a service name
            service = msg.pop(0)
            # Not first command in session or Reserved service name
            if worker_ready or service.startswith(self.INTERNAL_SERVICE_PREFIX):
                self.delete_worker(worker, True)
            else:
                # Attach worker to service and mark as idle
                worker.service = self.require_service(service)
                self.worker_waiting(worker)

        elif MDP.W_REPLY == command:
            if worker_ready:
                # Remove & save client return envelope and insert the
                # protocol header and service name, then rewrap envelope.
                client = msg.pop(0)
                empty = msg.pop(0)  # ?
                msg = [client, b"", MDP.C_CLIENT, worker.service.name] + msg
                self.socket.send_multipart(msg)
                self.worker_waiting(worker)
            else:
                self.delete_worker(worker, True)

        elif MDP.W_HEARTBEAT == command:
            if worker_ready:
                worker.expiry = time.time() + 1e-3 * self.HEARTBEAT_EXPIRY
            else:
                self.delete_worker(worker, True)

        elif MDP.W_DISCONNECT == command:
            self.delete_worker(worker, False)

        elif MDP.W_INVENTORY_REQUEST == command:
            assert len(msg) == 1  # received worker name
            if worker_ready:
                worker_name = msg.pop(0).decode("utf-8")
                msg = [
                    worker.address,
                    b"",
                    MDP.W_WORKER,
                    MDP.W_INVENTORY_REPLY,
                    json.dumps(None).encode("utf-8"),
                ]
                try:
                    msg[-1] = json.dumps(self.inventory.workers[worker_name]).encode(
                        "utf-8"
                    )
                except KeyError:
                    log.error(f"No inventory data found for '{worker_name}' worker")
                self.socket.send_multipart(msg)
                self.worker_waiting(worker)
            else:
                self.delete_worker(worker, True)

        else:
            log.error(f"invalid message: {msg}")

    def delete_worker(self, worker, disconnect):
        """Deletes worker from all data structures, and deletes worker."""
        assert worker is not None
        if disconnect:
            self.send_to_worker(worker, MDP.W_DISCONNECT, None, None)

        if worker.service is not None:
            worker.service.waiting.remove(worker)
        self.workers.pop(worker.identity, None)

    def require_worker(self, address):
        """Finds the worker (creates if necessary)."""
        assert address is not None
        identity = hexlify(address)
        worker = self.workers.get(identity)
        if worker is None:
            worker = Worker(identity, address, self.HEARTBEAT_EXPIRY)
            self.workers[identity] = worker
            log.info(f"registered new worker: {address}")

        return worker

    def require_service(self, name):
        """Locates the service (creates if necessary)."""
        assert name is not None
        service = self.services.get(name)
        if service is None:
            service = Service(name)
            self.services[name] = service
            log.debug(f"registered new service: {name}")

        return service

    def bind(self, endpoint):
        """Bind broker to endpoint, can call this multiple times.

        We use a single socket for both clients and workers.
        """
        self.socket.bind(endpoint)
        log.info(
            f"broker is active at '{endpoint}'",
        )

    def service_internal(self, service, msg):
        """Handle internal service according to 8/MMI specification"""
        try:
            data = json.loads(msg[-1])
        except Exception as e:
            log.exception(f"Failed to JSON decode message data for {service}:\n{e}")
            msg[-1] = str(e).encode("utf-8")
        else:
            if service == b"mmi.broker_utils":
                msg[-1] = self.broker_utils(data)
            elif service == b"mmi.service":
                name = data["service_name"]
                msg[-1] = b"200" if name.encode("utf-8") in self.services else b"404"
            else:
                msg[-1] = {
                    "error": f"Broker unsupported service: '{service.decode('utf-8')}'"
                }
                msg[-1] = json.dumps(msg[-1]).encode("utf-8")

        # insert the protocol header and service name after the routing envelope ([client, ''])
        msg = msg[:2] + [MDP.C_CLIENT, service] + msg[2:]
        log.debug(f"sending message to client: {msg}")
        self.socket.send_multipart(msg)

    def send_heartbeats(self):
        """Send heartbeats to idle workers if it's time"""
        if time.time() > self.heartbeat_at:
            for worker in self.waiting:
                self.send_to_worker(worker, MDP.W_HEARTBEAT, None, None)

            self.heartbeat_at = time.time() + 1e-3 * self.HEARTBEAT_INTERVAL

    def purge_workers(self):
        """Look for & kill expired workers.

        Workers are oldest to most recent, so we stop at the first alive worker.
        """
        while self.waiting:
            w = self.waiting[0]
            if w.expiry < time.time():
                log.info(
                    f"deleting expired worker: '{w.address}', identity '{w.identity}'"
                )
                self.delete_worker(w, False)
                self.waiting.pop(0)
            else:
                break

    def worker_waiting(self, worker):
        """This worker is now waiting for work."""
        # Queue to broker and service waiting lists
        self.waiting.append(worker)
        worker.service.waiting.append(worker)
        worker.expiry = time.time() + 1e-3 * self.HEARTBEAT_EXPIRY
        self.dispatch(service=worker.service, target_worker="any", msg=None)

    def dispatch(self, service, target_worker, msg):
        """
        Dispatch requests to waiting workers as possible
        
        :param service: service object
        :param target_worker: string indicating workers addresses to dispatch to
        :param msg: string with work request content
        """
        assert service is not None, "service name is None, must be a string"
        
        if msg is not None:  # Queue message if any
            service.requests.append((target_worker, msg,))
        self.purge_workers()
        
        # iterate over requests and try sending them to workers
        while service.requests:
            target_worker, msg = service.requests.pop(0)
            # anycast - send to any available worker
            if target_worker == b"any":
                if service.waiting: # check if has waiting workers
                    worker = service.waiting.pop(0)
                    self.waiting.remove(worker)
                    self.send_to_worker(worker, MDP.W_REQUEST, None, msg)
                else:
                    service.requests.append((target_worker, msg,))                     
            # unicast - send to specific worker by its address/name
            elif hexlify(target_worker) in self.workers:
                worker = self.workers[hexlify(target_worker)]
                service.waiting.remove(worker)
                self.waiting.remove(worker)
                self.send_to_worker(worker, MDP.W_REQUEST, None, msg)
            # reply back to client with error message
            else:
                message = f"{service.name} service no target worker {target_worker}"
                log.error(message)
                msg = [msg[0], b"", MDP.C_CLIENT, service.name, message.encode("utf-8")]
                self.socket.send_multipart(msg)


    def send_to_worker(self, worker, command, option, msg=None):
        """Send message to worker.

        If message is provided, sends that message.
        """

        if msg is None:
            msg = []
        elif not isinstance(msg, list):
            msg = [msg]

        # Stack routing and protocol envelopes to start of message
        # and routing envelope
        if option is not None:
            msg = [option] + msg
        msg = [worker.address, b"", MDP.W_WORKER, command] + msg

        log.debug(f"sending '{command}' to worker: {msg}")

        self.socket.send_multipart(msg)

    def broker_utils(self, data):
        task = data["task"]
        ret = f"Unsupported task '{task}'"
        if task == "show_workers":
            if self.workers:
                ret = [
                    {
                        "name": w.address.decode("utf-8"),
                        "identity": k.decode("utf-8"),
                        "service": w.service.name.decode("utf-8"),
                        "status": "active",
                    }
                    for k, w in self.workers.items()
                ]
            else:
                ret = [{"name": "", "identity": "", "service": "", "status": ""}]
        elif task == "show_broker":
            ret = {
                "address": self.socket.getsockopt_string(zmq.LAST_ENDPOINT),
                "status": "active",
                "heartbeat liveness": self.HEARTBEAT_LIVENESS,
                "heartbeat interval": self.HEARTBEAT_INTERVAL,
                "workers count": len(self.workers),
                "services count": len(self.services),
            }

        return json.dumps(ret).encode("utf-8")


def main():
    """create and start new broker"""
    broker = MajorDomoBroker()
    broker.bind("tcp://*:5555")
    broker.mediate()


if __name__ == "__main__":
    main()
