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
import zmq

from binascii import hexlify
from multiprocessing import Event
from typing import Union
from . import NFP
from .zhelpers import dump
from .inventory import NorFabInventory
from .keepalives import KeepAliver

log = logging.getLogger(__name__)

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
        elif command == NFP.EVENT:
            msg = [client, b"", NFP.CLIENT, NFP.EVENT, service] + message
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
        elif NFP.EVENT == command and worker.is_ready():
            client = msg.pop(0)
            empty = msg.pop(0)
            self.send_to_client(client, NFP.EVENT, worker.service.name, msg)
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
        ret = []
        if not service.workers:
            log.warning(
                f"NFPBroker - '{service.name}' has no active workers registered, try later"
            )
            ret = []
        elif target == b"any":
            ret = [service.workers[random.randint(0, len(service.workers) - 1)]]
        elif target == b"all":
            ret = service.workers
        elif target in self.workers:  # single worker
            ret = [self.workers[target]]
        else:  # target list of workers
            try:
                target = json.loads(target)
                if isinstance(target, list):
                    for w in target:
                        w = w.encode("utf-8")
                        if w in self.workers:
                            ret.append(self.workers[w])
                    ret = list(set(ret))  # dedup workers
            except Exception as e:
                log.error(
                    f"NFPBroker - Failed to load target '{target}' with error '{e}'"
                )
        return ret

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
            #provide list of all files from all subdirectories
            elif task == "walk":
                full_path = os.path.join(self.base_dir, url_path)
                if os.path.exists(full_path) and os.path.isdir(full_path):
                    reply = []
                    for root, dirs, files in os.walk(full_path):
                        # skip path containing folders like __folders__
                        if root.count("__") >= 2:
                            continue
                        root = root.replace(self.base_dir, "")
                        root = root.lstrip("\\")
                        root = root.replace("\\", "/")
                        for file in files:
                            # skip hidden/system files
                            if file.startswith("."):
                                continue
                            if root:
                                reply.append(f"nf://{root}/{file}")
                            else:
                                reply.append(f"nf://{file}")
                    reply = json.dumps(reply).encode("utf-8")
                else:
                    reply = json.dumps(["Directory Not Found"]).encode("utf-8")
        else:
            reply = f"fss.service.broker - unsupported url '{url}', task '{task}'"
            log.error(reply)

        if isinstance(reply, str):
            reply = reply.encode("utf-8")

        self.send_to_client(
            sender, NFP.RESPONSE, b"fss.service.broker", [uuid, status, reply]
        )
