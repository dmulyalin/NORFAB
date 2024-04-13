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
import threading
import random
import os
import hashlib

from binascii import hexlify
from multiprocessing import Event

import zmq

from . import MDP
from . import NFP
from .zhelpers import dump
from .inventory import NorFabInventory
from .keepalives import KeepAliver

log = logging.getLogger(__name__)


class Service(object):
    """a single Service"""

    name = None  # Service name
    requests = None  # List of client requests
    waiting = None  # List of waiting workers
    workers = None  # list of known workers

    def __init__(self, name):
        self.name = name
        self.requests = []
        self.waiting = []
        self.workers = []


class Worker(object):
    """a Worker, idle or active"""

    identity = None  # hex Identity of worker
    address = None  # Address to route to
    service = None  # Owning service, if known
    expiry = None  # expires at this point, unless heartbeat
    data = None  # store data published by worker

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
            worker.service.workers.remove(worker)
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
            else:
                msg[-1] = {
                    "error": f"404 service not found: '{service.decode('utf-8')}'"
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
        worker.service.workers.append(worker)
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
            service.requests.append(
                (
                    target_worker,
                    msg,
                )
            )
        self.purge_workers()

        # iterate over requests and try sending them to workers
        while service.requests:
            target_worker, msg = service.requests.pop(0)
            # anycast - send to any available worker
            if target_worker == b"any":
                if service.waiting:  # check if has waiting workers
                    worker = service.waiting.pop(0)
                    self.waiting.remove(worker)
                    self.send_to_worker(worker, MDP.W_REQUEST, None, msg)
                else:
                    service.requests.append(
                        (
                            target_worker,
                            msg,
                        )
                    )
            # broadcast - send message to all known workers for given service
            elif target_worker == b"all":
                for worker in service.workers:
                    self.send_to_worker(worker, MDP.W_REQUEST, None, msg)
            # unicast - send to specific worker by its name
            elif hexlify(target_worker) in self.workers:
                worker = self.workers[hexlify(target_worker)]
                service.waiting.remove(worker)
                self.waiting.remove(worker)
                self.send_to_worker(worker, MDP.W_REQUEST, None, msg)
            # reply back to client with error message
            else:
                message = (
                    f"{service.name} service can't target worker {target_worker}, target worker "
                    f"should be either 'all', 'any' or specific worker name"
                )
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


# ----------------------------------------------------------------------
# NORFAB Protocol Broker Implementation
# ----------------------------------------------------------------------


class NFPService(object):
    """A single NFP Service"""

    def __init__(self, name: str):
        self.name = name  # Service name
        self.workers = []  # list of known workers


class NFPWorker(object):
    """An NFP Worker convenience class"""

    def __init__(
        self,
        address: str,
        socket,
        socket_lock,
        multiplier: int,  # e.g. 6 times
        keepalive: int,  # e.g. 5000 ms
        service: NFPService = None,
        log_level: str = "WARNING",
    ):
        self.address = address  # Address to route to
        self.service = service
        self.ready = False
        self.socket = socket
        self.exit_event = threading.Event()
        self.keepalive = keepalive
        self.multiplier = multiplier
        self.socket_lock = socket_lock
        self.log_level = log_level

    def start_keepalives(self):
        self.keepaliver = KeepAliver(
            address=self.address,
            socket=self.socket,
            multiplier=self.multiplier,
            keepalive=self.keepalive,
            exit_event=self.exit_event,
            service=self.service.name,
            whoami=NFP.BROKER,
            name="NFPBroker",
            socket_lock=self.socket_lock,
            log_level=self.log_level,
        )
        self.keepaliver.start()

    def is_ready(self):
        """True if worker signaled W.READY"""
        return self.service is not None and self.ready is True

    def destroy(self, disconnect=False):
        """Clean up routine"""
        self.exit_event.set()
        self.keepaliver.stop()
        self.service.workers.remove(self)

        if disconnect is True:
            msg = [self.address, b"", NFP.WORKER, self.service.name, NFP.DISCONNECT]
            with self.socket_lock:
                self.socket.send_multipart(msg)


class NFPBroker:

    """
    NORFAB Protocol broker
    """

    def __init__(
        self,
        endpoint: str,
        exit_event: Event,
        inventory: NorFabInventory,
        log_level: str = "WARNING",
        multiplier: int = 6,
        keepalive: int = 2500,
        base_dir: str = "",
    ):
        """Initialize broker state."""
        log.setLevel(log_level.upper())
        self.log_level = log_level
        self.keepalive = keepalive
        self.multiplier = multiplier

        self.services = {}
        self.workers = {}
        self.exit_event = exit_event
        self.inventory = inventory

        self.ctx = zmq.Context()
        self.socket = self.ctx.socket(zmq.ROUTER)
        self.socket.linger = 0
        self.poller = zmq.Poller()
        self.poller.register(self.socket, zmq.POLLIN)
        self.socket.bind(endpoint)
        self.socket_lock = (
            threading.Lock()
        )  # used for keepalives to protect socket object

        self.base_dir = base_dir or os.getcwd()
        os.makedirs(self.base_dir, exist_ok=True)

        log.debug(f"NFPBroker - is read and listening on {endpoint}")

    def mediate(self):
        """
        Main broker work happens here

        Client send messages of this frame format:


        """
        while True:
            try:
                items = self.poller.poll(self.keepalive)
            except KeyboardInterrupt:
                break  # Interrupted

            if items:
                msg = self.socket.recv_multipart()
                log.debug(f"NFPBroker - received '{msg}'")

                sender = msg.pop(0)
                empty = msg.pop(0)
                header = msg.pop(0)

                if header == NFP.CLIENT:
                    self.process_client(sender, msg)
                elif header == NFP.WORKER:
                    self.process_worker(sender, msg)

            self.purge_workers()

            # check if need to stop
            if self.exit_event.is_set():
                self.destroy()
                break

    def destroy(self):
        """Disconnect all workers, destroy context."""
        log.info(f"NFPBroker - interrupt received, killing broker")
        for name in list(self.workers.keys()):
            # in case worker self destroyed while we iterating
            if self.workers.get(name):
                self.delete_worker(self.workers[name], True)
        self.ctx.destroy(0)

    def delete_worker(self, worker, disconnect):
        """Deletes worker from all data structures, and deletes worker."""
        worker.destroy(disconnect)
        self.workers.pop(worker.address, None)

    def purge_workers(self):
        """Look for & delete expired workers."""
        for name in list(self.workers.keys()):
            # in case worker self destroyed while we iterating
            if self.workers.get(name):
                w = self.workers[name]
            if not w.keepaliver.is_alive():
                self.delete_worker(w, False)

    def send_to_worker(
        self, worker: NFPWorker, command: bytes, sender: bytes, uuid: bytes, data: bytes
    ):
        """Send message to worker. If message is provided, sends that message."""
        # Stack routing and protocol envelopes to start of message
        if command == NFP.POST:
            msg = [worker.address, b"", NFP.WORKER, NFP.POST, sender, b"", uuid, data]
        elif command == NFP.GET:
            msg = [worker.address, b"", NFP.WORKER, NFP.GET, sender, b"", uuid, data]
        else:
            log.error(f"NFPBroker - invalid worker command: {command}")
            return
        with self.socket_lock:
            log.debug(f"NFPBroker - sending to worker '{msg}'")
            self.socket.send_multipart(msg)

    def send_to_client(self, client: str, command: str, service: str, message: list):
        """Send message to client."""
        # Stack routing and protocol envelopes to start of message
        if command == NFP.RESPONSE:
            msg = [client, b"", NFP.CLIENT, NFP.RESPONSE, service] + message
        else:
            log.error(f"NFPBroker - invalid client command: {command}")
            return
        with self.socket_lock:
            log.debug(f"NFPBroker - sending to client '{msg}'")
            self.socket.send_multipart(msg)

    def process_worker(self, sender, msg):
        """Process message received from worker."""
        command = msg.pop(0)
        worker = self.require_worker(sender)

        if NFP.READY == command and not worker.is_ready():
            service = msg.pop(0)
            worker.service = self.require_service(service)
            worker.ready = True
            worker.start_keepalives()
            worker.service.workers.append(worker)
        elif NFP.RESPONSE == command and worker.is_ready():
            client = msg.pop(0)
            empty = msg.pop(0)
            self.send_to_client(client, NFP.RESPONSE, worker.service.name, msg)
        elif NFP.KEEPALIVE == command:
            worker.keepaliver.received_heartbeat([worker.address] + msg)
        elif NFP.DISCONNECT == command and worker.is_ready():
            self.delete_worker(worker, False)
        elif not worker.is_ready():
            self.delete_worker(worker, disconnect=True)
        else:
            log.error(f"NFPBroker - invalid message: {msg}")

    def require_worker(self, address):
        """Finds the worker, creates if necessary."""
        if not self.workers.get(address):
            self.workers[address] = NFPWorker(
                address=address,
                socket=self.socket,
                multiplier=self.multiplier,
                keepalive=self.keepalive,
                socket_lock=self.socket_lock,
                log_level=self.log_level,
            )
            log.info(f"NFPBroker - registered new worker {address}")

        return self.workers[address]

    def require_service(self, name):
        """Locates the service (creates if necessary)."""
        if not self.services.get(name):
            service = NFPService(name)
            self.services[name] = service
            log.debug(f"NFPBroker - registered new service {name}")

        return self.services[name]

    def process_client(self, sender, msg):
        """Process a request coming from a client."""
        command = msg.pop(0)
        service = msg.pop(0)
        target = msg.pop(0)
        uuid = msg.pop(0)
        data = msg.pop(0)

        # check if valid command from client
        if command not in NFP.client_commands:
            message = f"NFPBroker - Unsupported client command '{command}'"
            log.error(message)
            self.send_to_client(
                sender, NFP.RESPONSE, service, [message.encode("utf-8")]
            )
        # Management Interface
        elif service == b"mmi.service.broker":
            self.mmi_service(sender, command, target, uuid, data)
        elif service == b"sid.service.broker":
            self.inventory_service(sender, command, target, uuid, data)
        elif service == b"fss.service.broker":
            self.file_sharing_service(sender, command, target, uuid, data)
        else:
            self.dispatch(
                sender, command, self.require_service(service), target, uuid, data
            )

    def filter_workers(self, target: bytes, service: NFPService) -> list:
        """
        Helper function to filter workers

        :param target: bytest string, workers target
        :param service: NFPService object
        """
        if not service.workers:
            return []
        elif target == b"any":
            return [service.workers[random.randint(0, len(service.workers) - 1)]]
        elif target == b"all":
            return service.workers
        elif target in self.workers:
            return [self.workers[target]]
        return []

    def dispatch(self, sender, command, service, target, uuid, data):
        """
        Dispatch requests to waiting workers as possible

        :param service: service object
        :param target: string indicating workers addresses to dispatch to
        :param msg: string with work request content
        """
        log.debug(
            f"NFPBroker - dispatching request to workers: sender '{sender}', "
            f"command '{command}', service '{service.name}', target '{target}'"
            f"data '{data}', uuid '{uuid}'"
        )
        self.purge_workers()
        workers = self.filter_workers(target, service)

        # handle case when service has no workers registered
        if not workers:
            message = f"NFPBroker - {service.name} service failed to target workers '{target}'"
            log.error(message)
            self.send_to_client(
                sender,
                NFP.RESPONSE,
                service.name,
                [uuid, b"400", message.encode("utf-8")],
            )
        else:
            # inform client that JOB dispatched
            w_addresses = [w.address.decode("utf-8") for w in workers]
            self.send_to_client(
                sender,
                NFP.RESPONSE,
                service.name,
                [
                    uuid,
                    b"202",
                    json.dumps(
                        {
                            "workers": w_addresses,
                            "uuid": uuid.decode("utf-8"),
                            "target": target.decode("utf-8"),
                            "status": "DISPATCHED",
                            "service": service.name.decode("utf-8"),
                        }
                    ).encode("utf-8"),
                ],
            )
            # send job to workers
            for worker in workers:
                self.send_to_worker(worker, command, sender, uuid, data)

    def mmi_service(self, sender, command, target, uuid, data):
        """Handle internal service according to 8/MMI specification"""
        log.debug(
            f"mmi.service.broker - processing request: sender '{sender}', "
            f"command '{command}', target '{target}'"
            f"data '{data}', uuid '{uuid}'"
        )
        data = json.loads(data)
        task = data.get("task")
        args = data.get("args", [])
        kwargs = data.get("kwargs", {})
        ret = f"Unsupported task '{task}'"
        if task == "show_workers":
            if self.workers:
                ret = [
                    {
                        "name": w.address.decode("utf-8"),
                        "service": w.service.name.decode("utf-8"),
                        "status": "alive" if w.keepaliver.is_alive() else "dead",
                        "holdtime": str(w.keepaliver.show_holdtime()),
                        "keepalives tx/rx": f"{w.keepaliver.keepalives_send} / {w.keepaliver.keepalives_received}",
                        "alive (s)": str(w.keepaliver.show_alive_for()),
                    }
                    for k, w in self.workers.items()
                ]
                # filter reply
                service = kwargs.get("service")
                status = kwargs.get("status")
                if service and service != "all":
                    ret = [w for w in ret if w["service"] == service]
                if status in ["alive", "dead"]:
                    ret = [w for w in ret if w["status"] == status]
                if not ret:
                    ret = [{"name": "", "service": "", "status": ""}]
            else:
                ret = [{"name": "", "service": "", "status": ""}]
        elif task == "show_broker":
            ret = {
                "address": self.socket.getsockopt_string(zmq.LAST_ENDPOINT),
                "status": "active",
                "multiplier": self.multiplier,
                "keepalive": self.keepalive,
                "workers count": len(self.workers),
                "services count": len(self.services),
                "base_dir": self.base_dir,
            }
        reply = json.dumps(ret).encode("utf-8")
        self.send_to_client(
            sender, NFP.RESPONSE, b"mmi.service.broker", [uuid, b"200", reply]
        )

    def inventory_service(self, sender, command, target, uuid, data):
        log.debug(
            f"sid.service.broker - processing request: sender '{sender}', "
            f"command '{command}', target '{target}'"
            f"data '{data}', uuid '{uuid}'"
        )
        data = json.loads(data)
        task = data.get("task")
        args = data.get("args", [])
        kwargs = data.get("kwargs", {})
        ret = f"Unsupported task '{task}'"
        if task == "get_inventory":
            name = kwargs["name"]
            try:
                ret = self.inventory.workers[name]
            except KeyError:
                log.error(f"sid.service.broker - no inventory data found for '{name}'")
                ret = None

        reply = json.dumps(ret).encode("utf-8")
        self.send_to_client(
            sender, NFP.RESPONSE, b"sid.service.broker", [uuid, b"200", reply]
        )

    def file_sharing_service(self, sender, command, target, uuid, data):
        log.debug(
            f"fss.service.broker - processing request: sender '{sender}', "
            f"command '{command}', target '{target}'"
            f"data '{data}', uuid '{uuid}'"
        )
        data = json.loads(data)
        task = data.get("task")
        kwargs = data.get("kwargs", {})
        url = kwargs.get("url")
        reply = f"Unsupported task '{task}'"
        status = b"200"
        if url is None:
            reply = "No file URL provided"
        elif url.startswith("nf://"):
            url_path = url.replace("nf://", "")
            if task == "fetch_file":
                chunk_size = int(kwargs["chunk_size"])
                offset = int(kwargs["offset"])  # number of chunks to offset
                full_path = os.path.join(self.base_dir, url_path)
                if os.path.exists(full_path):
                    with open(full_path, "rb") as f:
                        f.seek(offset, os.SEEK_SET)
                        reply = f.read(chunk_size)
                else:
                    reply = f"Not Found '{full_path}'"
            elif task == "list_files":
                full_path = os.path.join(self.base_dir, url_path)
                if os.path.exists(full_path) and os.path.isdir(full_path):
                    reply = os.listdir(full_path)
                    reply = json.dumps(reply).encode("utf-8")
                else:
                    reply = json.dumps(["Directory Not Found"]).encode("utf-8")
            elif task == "file_details":
                full_path = os.path.join(self.base_dir, url_path)
                exists = os.path.exists(full_path) and os.path.isfile(full_path)
                # calculate md5 hash
                md5hash = None
                if exists:
                    with open(full_path, "rb") as f:
                        file_hash = hashlib.md5()
                        chunk = f.read(8192)
                        while chunk:
                            file_hash.update(chunk)
                            chunk = f.read(8192)
                    md5hash = file_hash.hexdigest()
                # calculate file size
                size = None
                if exists:
                    size = os.path.getsize(full_path)
                reply = json.dumps(
                    {
                        "md5hash": md5hash,
                        "size_bytes": size,
                        "exists": exists,
                    }
                )
        else:
            reply = f"fss.service.broker - unsupported url '{url}', task '{task}'"
            log.error(reply)

        if isinstance(reply, str):
            reply = reply.encode("utf-8")

        self.send_to_client(
            sender, NFP.RESPONSE, b"fss.service.broker", [uuid, status, reply]
        )
