import logging
import sys
import json
import threading
import random
import os
import hashlib
import zmq
import zmq.auth
import signal
import importlib.metadata

from zmq.auth.thread import ThreadAuthenticator
from binascii import hexlify
from multiprocessing import Event
from typing import Union, Any, List
from . import NFP
from .zhelpers import dump
from .inventory import NorFabInventory, logging_config_producer
from .keepalives import KeepAliver
from .security import generate_certificates

log = logging.getLogger(__name__)

signal.signal(signal.SIGINT, signal.SIG_IGN)

# ----------------------------------------------------------------------
# NORFAB Protocol Broker Implementation
# ----------------------------------------------------------------------


class NFPService(object):
    """A single NFP Service"""

    def __init__(self, name: str):
        self.name = name  # Service name
        self.workers = []  # list of known workers


class NFPWorker(object):
    """
    An NFP Worker convenience class.

    Attributes:
        service (NFPService): The service instance.
        ready (bool): Indicates if the worker is ready.
        exit_event (threading.Event): Event to signal exit.
        keepalive (int): Keepalive interval in milliseconds.
        multiplier (int): Multiplier value.

    Methods:
        start_keepalives():
            Starts the keepalive process for the worker.
        is_ready() -> bool:
            Checks if the worker has signaled W.READY.
        destroy(disconnect=False):
            Cleans up the worker, optionally disconnecting it.

    Args:
        address (str): Address to route to.
        socket: The socket object used for communication.
        socket_lock: The lock object to synchronize socket access.
        multiplier (int): Multiplier value, e.g., 6 times.
        keepalive (int): Keepalive interval in milliseconds, e.g., 5000 ms.
        service (NFPService, optional): The service instance. Defaults to None.
    """

    def __init__(
        self,
        address: str,
        socket,
        socket_lock,
        multiplier: int,  # e.g. 6 times
        keepalive: int,  # e.g. 5000 ms
        service: NFPService = None,
    ):
        self.address = address  # Address to route to
        self.service = service
        self.ready = False
        self.socket = socket
        self.exit_event = threading.Event()
        self.keepalive = keepalive
        self.multiplier = multiplier
        self.socket_lock = socket_lock

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
        )
        self.keepaliver.start()

    def is_ready(self):
        """
        Check if the worker is ready.

        Returns:
            bool: True if the worker has signaled readiness (W.READY) and the service is not None, otherwise False.
        """
        return self.service is not None and self.ready is True

    def destroy(self, disconnect=False):
        """
        Clean up routine for the broker.

        This method performs the following actions:

        1. Sets the exit event to signal termination.
        2. Stops the keepaliver if it exists.
        3. Removes the current worker from the service's worker list.
        4. Optionally sends a disconnect message to the broker if `disconnect` is True.

        Args:
            disconnect (bool): If True, sends a disconnect message to the broker.
        """
        self.exit_event.set()
        if hasattr(self, "keepaliver"):
            self.keepaliver.stop()
        self.service.workers.remove(self)

        if disconnect is True:
            msg = [self.address, b"", NFP.WORKER, self.service.name, NFP.DISCONNECT]
            with self.socket_lock:
                self.socket.send_multipart(msg)


class NFPBroker:
    """
    Attributes:
        private_keys_dir (str): Directory for private keys.
        public_keys_dir (str): Directory for public keys.
        broker_private_key_file (str): File path for broker's private key.
        broker_public_key_file (str): File path for broker's public key.
        keepalive (int): The keepalive interval.
        multiplier (int): The multiplier value.
        services (dict): A dictionary to store services.
        workers (dict): A dictionary to store workers.
        exit_event (Event): The event to signal the broker to exit.
        inventory (NorFabInventory): The inventory object.
        base_dir (str): The base directory path from the inventory.
        broker_base_dir (str): The broker's base directory path.
        ctx (zmq.Context): The ZeroMQ context.
        auth (ThreadAuthenticator): The authenticator for the ZeroMQ context.
        socket (zmq.Socket): The ZeroMQ socket.
        poller (zmq.Poller): The ZeroMQ poller.
        socket_lock (threading.Lock): The lock to protect the socket object.

    Methods:
        setup_logging(self, log_queue, log_level: str) -> None:
            Method to apply logging configuration.
        mediate(self):
            Main broker work happens here.
        destroy(self):
            Disconnect all workers, destroy context.
        delete_worker(self, worker, disconnect):
            Deletes worker from all data structures, and deletes worker.
        purge_workers(self):
            Look for & delete expired workers.
        send_to_worker(self, worker: NFPWorker, command: bytes, sender: bytes, uuid: bytes, data: bytes):
            Send message to worker. If message is provided, sends that message.
        send_to_client(self, client: str, command: str, service: str, message: list):
            Send message to client.
        process_worker(self, sender, msg):
            Process message received from worker.
        require_worker(self, address):
            Finds the worker, creates if necessary.
        require_service(self, name):
            Locates the service (creates if necessary).
        process_client(self, sender, msg):
            Process a request coming from a client.
        filter_workers(self, target: bytes, service: NFPService) -> list:
            Helper function to filter workers.
        dispatch(self, sender, command, service, target, uuid, data):
            Dispatch requests to waiting workers as possible.
        mmi_service(self, sender, command, target, uuid, data):
            Handle internal service according to 8/MMI specification.
        inventory_service(self, sender, command, target, uuid, data):
            Handle inventory service requests.
        file_sharing_service(self, sender, command, target, uuid, data):
            Handle file sharing service requests.

    Args:
        endpoint (str): The endpoint address for the broker to bind to.
        exit_event (Event): An event to signal the broker to exit.
        inventory (NorFabInventory): The inventory object containing configuration and state.
        log_level (str, optional): The logging level. Defaults to None.
        log_queue (object, optional): The logging queue. Defaults to None.
        multiplier (int, optional): A multiplier value for internal use. Defaults to 6.
        keepalive (int, optional): The keepalive interval in milliseconds. Defaults to 2500.
        init_done_event (Event, optional): An event to signal that initialization is done. Defaults to None.
    """

    private_keys_dir = None
    public_keys_dir = None
    broker_private_key_file = None
    broker_public_key_file = None

    def __init__(
        self,
        endpoint: str,
        exit_event: Event,
        inventory: NorFabInventory,
        log_level: str = None,
        log_queue: object = None,
        multiplier: int = 6,
        keepalive: int = 2500,
        init_done_event: Event = None,
    ):
        self.setup_logging(log_queue, log_level)
        self.keepalive = keepalive
        self.multiplier = multiplier
        init_done_event = init_done_event or Event()

        self.services = {}
        self.workers = {}
        self.exit_event = exit_event
        self.inventory = inventory

        self.base_dir = self.inventory.base_dir
        self.broker_base_dir = os.path.join(
            self.base_dir, "__norfab__", "files", "broker"
        )
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.broker_base_dir, exist_ok=True)

        # generate certificates, create directories and load certs
        generate_certificates(
            self.broker_base_dir, cert_name="broker", inventory=inventory
        )
        self.private_keys_dir = os.path.join(self.broker_base_dir, "private_keys")
        self.public_keys_dir = os.path.join(self.broker_base_dir, "public_keys")
        self.broker_private_key_file = os.path.join(
            self.private_keys_dir, "broker.key_secret"
        )
        self.broker_public_key_file = os.path.join(self.public_keys_dir, "broker.key")
        server_public, server_secret = zmq.auth.load_certificate(
            self.broker_private_key_file
        )

        self.ctx = zmq.Context()

        # Start an authenticator for this context.
        self.auth = ThreadAuthenticator(self.ctx)
        self.auth.start()
        # self.auth.allow("0.0.0.0")
        self.auth.allow_any = True
        # Tell the authenticator how to handle CURVE requests
        self.auth.configure_curve(location=zmq.auth.CURVE_ALLOW_ANY)

        self.socket = self.ctx.socket(zmq.ROUTER)
        self.socket.curve_secretkey = server_secret
        self.socket.curve_publickey = server_public
        self.socket.curve_server = True  # must come before bind
        self.socket.linger = 0
        self.poller = zmq.Poller()
        self.poller.register(self.socket, zmq.POLLIN)
        self.socket.bind(endpoint)
        self.socket_lock = (
            threading.Lock()
        )  # used for keepalives to protect socket object

        init_done_event.set()  # signal finished initializing broker
        log.debug(f"NFPBroker - is ready and listening on {endpoint}")

    def setup_logging(self, log_queue, log_level: str) -> None:
        """
        Configures logging for the application.

        This method sets up the logging configuration using a provided log queue and log level.
        It updates the logging configuration dictionary with the given log queue and log level,
        and then applies the configuration using `logging.config.dictConfig`.

        Args:
            log_queue (queue.Queue): The queue to be used for logging.
            log_level (str): The logging level to be set. If None, the default level is used.

        Returns:
            None
        """
        logging_config_producer["handlers"]["queue"]["queue"] = log_queue
        if log_level is not None:
            logging_config_producer["root"]["level"] = log_level
        logging.config.dictConfig(logging_config_producer)

    def mediate(self):
        """
        Main broker work happens here.

        This method continuously polls for incoming messages and processes them
        based on their headers. It handles messages from clients and workers,
        and purges inactive workers periodically. The method also checks for an
        exit event to gracefully shut down the broker.

        Raises:
            KeyboardInterrupt: If the process is interrupted by a keyboard signal.
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
        """
        Disconnect all workers and destroy the context.

        This method performs the following actions:

        1. Logs an interrupt message indicating that the broker is being killed.
        2. Iterates through all
        """
        log.info(f"NFPBroker - interrupt received, killing broker")
        for name in list(self.workers.keys()):
            # in case worker self destroyed while we iterating
            if self.workers.get(name):
                self.delete_worker(self.workers[name], True)
        self.auth.stop()
        self.ctx.destroy(0)

    def delete_worker(self, worker, disconnect):
        """
        Deletes a worker from all data structures and destroys the worker.

        Args:
            worker (Worker): The worker instance to be deleted.
            disconnect (bool): A flag indicating whether to disconnect the worker before deletion.

        Returns:
            None
        """
        worker.destroy(disconnect)
        self.workers.pop(worker.address, None)

    def purge_workers(self):
        """
        Look for and delete expired workers.

        This method iterates through the list of workers and checks if each worker's
        keepalive thread is still alive. If a worker's keepalive thread is not alive,
        the worker is considered expired and is deleted from the list of workers.
        Additionally, a log message is generated indicating that the worker's keepalive
        has expired.

        Note:
            The method handles the case where a worker might be destroyed while
            iterating through the list of workers.

        Logging:
            Logs an info message when a worker's keepalive has expired, including the
            worker's address.
        """
        for name in list(self.workers.keys()):
            # in case worker self destroyed while we iterating
            if self.workers.get(name):
                w = self.workers[name]
            if not w.keepaliver.is_alive():
                self.delete_worker(w, False)
                log.info(
                    f"NFPBroker - {w.address.decode(encoding='utf-8')} worker keepalives expired"
                )

    def send_to_worker(
        self, worker: NFPWorker, command: bytes, sender: bytes, uuid: bytes, data: bytes
    ) -> None:
        """
        Send a message to a worker. If a message is provided, sends that message.

        Args:
            worker (NFPWorker): The worker to send the message to.
            command (bytes): The command to send (e.g., NFP.POST or NFP.GET).
            sender (bytes): The sender's identifier.
            uuid (bytes): The unique identifier for the message.
            data (bytes): The data to be sent with the message.

        Logs:
            Logs an error if the command is invalid.
            Logs a debug message when sending the message to the worker.
        """
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

    def send_to_client(
        self, client: str, command: str, service: str, message: list
    ) -> None:
        """
        Send a message to a specified client.

        Args:
            client (str): The identifier of the client to send the message to.
            command (str): The command type, either 'RESPONSE' or 'EVENT'.
            service (str): The service associated with the message.
            message (list): The message content to be sent.
        """

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

    def process_worker(self, sender: str, msg: list):
        """
        Process message received from worker.

        Parameters:
            sender (str): The identifier of the sender (worker).
            msg (list): The message received from the worker, where the first element is the command.

        Commands:

        - NFP.READY: Marks the worker as ready and assigns a service to it.
        - NFP.RESPONSE: Sends a response to a client.
        - NFP.KEEPALIVE: Processes a keepalive message from the worker.
        - NFP.DISCONNECT: Handles worker disconnection.
        - NFP.EVENT: Sends an event to a client.

        If the worker is not ready and an invalid command is received, the worker is deleted.

        Raises:
            AttributeError: If the worker does not have the required attributes for certain commands.
            IndexError: If the message list does not contain the expected number of elements for certain commands.
        """
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
        elif NFP.KEEPALIVE == command and hasattr(worker, "keepaliver"):
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
        """
        Finds the worker associated with the given address, creating a new worker if necessary.

        Args:
            address (str): The address of the worker to find or create.

        Returns:
            NFPWorker: The worker associated with the given address.
        """
        if not self.workers.get(address):
            self.workers[address] = NFPWorker(
                address=address,
                socket=self.socket,
                multiplier=self.multiplier,
                keepalive=self.keepalive,
                socket_lock=self.socket_lock,
            )
            log.info(
                f"NFPBroker - registered new worker {address.decode(encoding='utf-8')}"
            )

        return self.workers[address]

    def require_service(self, name):
        """
        Locates the service by name, creating it if necessary.

        Args:
            name (str): The name of the service to locate or create.

        Returns:
            NFPService: The located or newly created service instance.
        """
        if not self.services.get(name):
            service = NFPService(name)
            self.services[name] = service
            log.debug(
                f"NFPBroker - registered new service {name.decode(encoding='utf-8')}"
            )

        return self.services[name]

    def process_client(self, sender: str, msg: list) -> None:
        """
        Process a request coming from a client.

        Args:
            sender (str): The identifier of the client sending the request.
            msg (list): The message received from the client, expected to be a list where the first five elements are:
                - command (str): The command issued by the client.
                - service (str): The service to which the command is directed.
                - target (str): The target of the command.
                - uuid (str): The unique identifier for the request.
                - data (any): The data associated with the request.

        Raises:
            ValueError: If the command is not recognized as a valid client command.

        The method processes the command by:
            - Checking if the command is valid.
            - Routing the request to the appropriate service handler based on the service specified.
            - Sending an error message back to the client if the command is unsupported.
        """
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

        Args:
            target: bytest string, workers target
            service: NFPService object
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

    def dispatch(
        self,
        sender: str,
        command: bytes,
        service: object,
        target: Union[str, List[str]],
        uuid: str,
        data: Any,
    ) -> None:
        """
        Dispatch requests to waiting workers as possible

        Args:
            sender (str): The sender of the request.
            command (bytes): The command to be executed by the workers.
            service (Service): The service object associated with the request.
            target (str): A string indicating the addresses of the workers to dispatch to.
            uuid (str): A unique identifier for the request.
            data (Any): The data to be sent to the workers.
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
        """
        Handle internal broker Management Interface (MMI) service tasks.

        Parameters:
            sender (str): The sender of the request.
            command (str): The command to be executed.
            target (str): The target of the command.
            uuid (str): The unique identifier for the request.
            data (str): The data payload in JSON format.

        Supported MMI Tasks:

        - "show_workers": Returns a list of workers with their details.
        - "show_broker": Returns broker details including endpoint, status, keepalives, workers count, services count, directories, and security.
        - "show_broker_version": Returns the version of various packages and the platform.
        - "show_broker_inventory": Returns the broker's inventory.

        The response is sent back to the client in a format of JSON formatted string.
        """
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
                "endpoint": self.socket.getsockopt_string(zmq.LAST_ENDPOINT),
                "status": "active",
                "keepalives": {
                    "interval": self.keepalive,
                    "multiplier": self.multiplier,
                },
                "workers count": len(self.workers),
                "services count": len(self.services),
                "directories": {
                    "base-dir": self.base_dir,
                    "private-keys-dir": self.private_keys_dir,
                    "public-keys-dir": self.public_keys_dir,
                },
                "security": {
                    "broker-private-key-file": self.broker_private_key_file,
                    "broker-public-key-file": self.broker_public_key_file,
                },
            }
        elif task == "show_broker_version":
            ret = {
                "norfab": "",
                "pyyaml": "",
                "pyzmq": "",
                "psutil": "",
                "tornado": "",
                "jinja2": "",
                "python": sys.version.split(" ")[0],
                "platform": sys.platform,
            }
            # get version of packages installed
            for pkg in ret.keys():
                try:
                    ret[pkg] = importlib.metadata.version(pkg)
                except importlib.metadata.PackageNotFoundError:
                    pass
        elif task == "show_broker_inventory":
            ret = self.inventory.dict()
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
            # provide list of all files from all subdirectories
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
