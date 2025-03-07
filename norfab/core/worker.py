import logging
import time
import zmq
import json
import traceback
import threading
import queue
import os
import pickle
import psutil
import signal

from .zhelpers import dump
from . import NFP
from uuid import uuid4
from .client import NFPClient
from .keepalives import KeepAliver
from .security import generate_certificates
from .inventory import logging_config_producer
from typing import Any, Callable, Dict, List, Optional, Union
from .exceptions import NorfabJobFailedError
from .models import NorFabEvent
from norfab.core.inventory import NorFabInventory
from jinja2 import Environment
from jinja2.nodes import Include

log = logging.getLogger(__name__)

signal.signal(signal.SIGINT, signal.SIG_IGN)
# --------------------------------------------------------------------------------------------
# NORFAB Worker watchdog Object
# --------------------------------------------------------------------------------------------


class WorkerWatchDog(threading.Thread):
    """
    Class to monitor worker performance.

    Attributes:
        worker (object): The worker instance being monitored.
        worker_process (psutil.Process): The process of the worker.
        watchdog_interval (int): Interval in seconds for the watchdog to check the worker's status.
        memory_threshold_mbyte (int): Memory usage threshold in megabytes.
        memory_threshold_action (str): Action to take when memory threshold is exceeded ("log" or "shutdown").
        runs (int): Counter for the number of times the watchdog has run.
        watchdog_tasks (list): List of additional tasks to run during each watchdog interval.

    Methods:
        check_ram(): Checks the worker's RAM usage and takes action if it exceeds the threshold.
        get_ram_usage(): Returns the worker's RAM usage in megabytes.
        run(): Main loop of the watchdog thread, periodically checks the worker's status and runs tasks.

    Args:
        worker (object): The worker object containing inventory attributes.
    """

    def __init__(self, worker):
        super().__init__()
        self.worker = worker
        self.worker_process = psutil.Process(os.getpid())

        # extract inventory attributes
        self.watchdog_interval = worker.inventory.get("watchdog_interval", 30)
        self.memory_threshold_mbyte = worker.inventory.get(
            "memory_threshold_mbyte", 1000
        )
        self.memory_threshold_action = worker.inventory.get(
            "memory_threshold_action", "log"
        )

        # initiate variables
        self.runs = 0
        self.watchdog_tasks = []

    def check_ram(self):
        """
        Checks the current RAM usage and performs an action if it exceeds the threshold.

        This method retrieves the current RAM usage and compares it to the predefined
        memory threshold. If the RAM usage exceeds the threshold, it performs an action
        based on the `memory_threshold_action` attribute. The possible actions are:

        - "log": Logs a warning message.
        - "shutdown": Raises a SystemExit exception to terminate the program.

        Raises:
            SystemExit: If the memory usage exceeds the threshold and the action is "shutdown".
        """
        mem_usage = self.get_ram_usage()
        if mem_usage > self.memory_threshold_mbyte:
            if self.memory_threshold_action == "log":
                log.warning(
                    f"{self.name} watchdog, '{self.memory_threshold_mbyte}' "
                    f"memory_threshold_mbyte exceeded, memory usage "
                    f"{mem_usage}MByte"
                )
            elif self.memory_threshold_action == "shutdown":
                raise SystemExit(
                    f"{self.name} watchdog, '{self.memory_threshold_mbyte}' "
                    f"memory_threshold_mbyte exceeded, memory usage "
                    f"{mem_usage}MByte, killing myself"
                )

    def get_ram_usage(self):
        """
        Get the RAM usage of the worker process.

        Returns:
            float: The RAM usage in megabytes.
        """
        return self.worker_process.memory_info().rss / 1024000

    def run(self):
        """
        Executes the worker's watchdog main loop, periodically running tasks and checking conditions.
        The method performs the following steps in a loop until the worker's exit event is set:

        1. Sleeps in increments of 0.1 seconds until the total sleep time reaches the watchdog interval.
        2. Runs built-in tasks such as checking RAM usage.
        3. Executes additional tasks provided by child classes.
        4. Updates the run counter.
        5. Resets the sleep counter to start the cycle again.

        Attributes:
            slept (float): The total time slept in the current cycle.
        """
        slept = 0
        while not self.worker.exit_event.is_set():
            # continue sleeping for watchdog_interval
            if slept < self.watchdog_interval:
                time.sleep(0.1)
                slept += 0.1
                continue

            # run built in tasks:
            self.check_ram()

            # run child classes tasks
            for task in self.watchdog_tasks:
                task()

            # update counters
            self.runs += 1

            slept = 0  # reset to go to sleep


# --------------------------------------------------------------------------------------------
# NORFAB Worker Results Object
# --------------------------------------------------------------------------------------------


class Result:
    """
    NorFab Task Result class.

    Args:
        result (Any): Result of the task execution, see task's documentation for details.
        failed (bool): Whether the execution failed or not.
        errors (Optional[List[str]]): Exception thrown during the execution of the task (if any).
        task (str): Task function name that produced the results.
        messages (Optional[List[str]]): List of messages produced by the task.
        juuid (Optional[str]): Job UUID associated with the task.

    Methods:
        __repr__(): Returns a string representation of the Result object.
        __str__(): Returns a string representation of the result or errors.
        raise_for_status(message=""): Raises an error if the job failed.
        dictionary(): Serializes the result to a dictionary.
    """

    def __init__(
        self,
        result: Any = None,
        failed: bool = False,
        errors: Optional[List[str]] = None,
        task: str = None,
        messages: Optional[List[str]] = None,
        juuid: Optional[str] = None,
    ) -> None:
        self.task = task
        self.result = result
        self.failed = failed
        self.errors = errors or []
        self.messages = messages or []
        self.juuid = juuid

    def __repr__(self) -> str:
        """
        Return a string representation of the object.

        The string representation includes the class name and the task attribute.

        Returns:
            str: A string in the format 'ClassName: "task"'.
        """
        return '{}: "{}"'.format(self.__class__.__name__, self.task)

    def __str__(self) -> str:
        """
        Returns a string representation of the object.

        If there are errors, it joins them with two newline characters and returns the result.
        Otherwise, it returns the string representation of the result.

        Returns:
            str: The string representation of the errors or the result.
        """
        if self.errors:
            return str("\n\n".join(self.errors))

        return str(self.result)

    def raise_for_status(self, message=""):
        """
        Raises a NorfabJobFailedError if the job has failed.

        Parameters:
            message (str): Optional. Additional message to include in the error. Default is an empty string.

        Raises:
            NorfabJobFailedError: If the job has failed, this error is raised with the provided message and the list of errors.
        """
        if self.failed:
            if message:
                raise NorfabJobFailedError(
                    f"{message}; Errors: {'; '.join(self.errors)}"
                )
            else:
                raise NorfabJobFailedError(f"Errors: {'; '.join(self.errors)}")

    def dictionary(self):
        """
        Serialize the result to a dictionary.

        This method converts the instance attributes to a dictionary format.
        It ensures that the `errors` and `messages` attributes are lists.

        Returns:
            dict: A dictionary containing the following keys:

                - task: The task associated with the worker.
                - failed: A boolean indicating if the task failed.
                - errors: A list of errors encountered during the task.
                - result: The result of the task.
                - messages: A list of messages related to the task.
                - juuid: The unique identifier for the job.
        """
        if not isinstance(self.errors, list):
            self.errors = [self.errors]
        if not isinstance(self.messages, list):
            self.messages = [self.messages]

        return {
            "task": self.task,
            "failed": self.failed,
            "errors": self.errors,
            "result": self.result,
            "messages": self.messages,
            "juuid": self.juuid,
        }


# --------------------------------------------------------------------------------------------
# NIRFAB worker, credits to https://rfc.zeromq.org/spec/9/
# --------------------------------------------------------------------------------------------

file_write_lock = threading.Lock()
queue_file_lock = threading.Lock()


def dumper(data, filename):
    """
    Serializes and saves data to a file using pickle.

    Args:
        data (any): The data to be serialized and saved.
        filename (str): The name of the file where the data will be saved.
    """
    with file_write_lock:
        with open(filename, "wb") as f:
            pickle.dump(data, f)


def loader(filename):
    """
    Load and deserialize a Python object from a file.

    This function opens a file in binary read mode, reads its content, and
    deserializes it using the pickle module. The file access is synchronized
    using a file write lock to ensure thread safety.

    Args:
        filename (str): The path to the file to be loaded.

    Returns:
        object: The deserialized Python object from the file.
    """
    with file_write_lock:
        with open(filename, "rb") as f:
            return pickle.load(f)


def request_filename(suuid: Union[str, bytes], base_dir_jobs: str):
    """
    Returns a freshly allocated request filename for the given UUID string.

    Args:
        suuid (Union[str, bytes]): The UUID string or bytes.
        base_dir_jobs (str): The base directory where job files are stored.

    Returns:
        str: The full path to the request file with the given UUID.
    """
    suuid = suuid.decode("utf-8") if isinstance(suuid, bytes) else suuid
    return os.path.join(base_dir_jobs, f"{suuid}.req")


def reply_filename(suuid: Union[str, bytes], base_dir_jobs: str):
    """
    Returns a freshly allocated reply filename for the given UUID string.

    Args:
        suuid (Union[str, bytes]): The UUID string or bytes.
        base_dir_jobs (str): The base directory where job files are stored.

    Returns:
        str: The full path to the reply file with the given UUID.
    """
    suuid = suuid.decode("utf-8") if isinstance(suuid, bytes) else suuid
    return os.path.join(base_dir_jobs, f"{suuid}.rep")


def event_filename(suuid: Union[str, bytes], base_dir_jobs: str):
    """
    Returns a freshly allocated event filename for the given UUID string.

    Args:
        suuid (Union[str, bytes]): The UUID string or bytes.
        base_dir_jobs (str): The base directory where job files are stored.

    Returns:
        str: The full path to the event file with the given UUID.
    """
    suuid = suuid.decode("utf-8") if isinstance(suuid, bytes) else suuid
    return os.path.join(base_dir_jobs, f"{suuid}.event")


def _post(worker, post_queue, queue_filename, destroy_event, base_dir_jobs):
    """
    Thread to receive POST requests and save them to hard disk.

    Args:
        worker (Worker): The worker instance handling the request.
        post_queue (queue.Queue): The queue from which POST requests are received.
        queue_filename (str): The filename where the job queue is stored.
        destroy_event (threading.Event): Event to signal the thread to stop.
        base_dir_jobs (str): The base directory where job files are stored.

    Functionality:
        - Ensures the message directory exists.
        - Continuously processes POST requests from the queue until the destroy event is set.
        - Saves the request to the hard disk.
        - Writes a reply indicating the job is pending.
        - Adds the job request to the queue file.
        - Sends an acknowledgment back to the client.
    """
    # Ensure message directory exists
    if not os.path.exists(base_dir_jobs):
        os.mkdir(base_dir_jobs)

    while not destroy_event.is_set():
        try:
            work = post_queue.get(block=True, timeout=0.1)
        except queue.Empty:
            continue
        timestamp = time.ctime()
        client_address = work[0]
        suuid = work[2]
        filename = request_filename(suuid, base_dir_jobs)
        dumper(work, filename)

        # write reply for this job indicating it is pending
        filename = reply_filename(suuid, base_dir_jobs)
        dumper(
            [
                client_address,
                b"",
                suuid,
                b"300",
                json.dumps(
                    {
                        "worker": worker.name,
                        "uuid": suuid.decode("utf-8"),
                        "status": "PENDING",
                        "service": worker.service.decode("utf-8"),
                    }
                ).encode("utf-8"),
            ],
            filename,
        )
        log.debug(f"{worker.name} - '{suuid}' job, saved PENDING reply filename")

        # add job request to the queue_filename
        with queue_file_lock:
            with open(queue_filename, "ab") as f:
                f.write(f"{suuid.decode('utf-8')}--{timestamp}\n".encode("utf-8"))
        log.debug(f"{worker.name} - '{suuid}' job, added job to queue filename")

        # ack job back to client
        worker.send_to_broker(
            NFP.RESPONSE,
            [
                client_address,
                b"",
                suuid,
                b"202",
                json.dumps(
                    {
                        "worker": worker.name,
                        "uuid": suuid.decode("utf-8"),
                        "status": "ACCEPTED",
                        "service": worker.service.decode("utf-8"),
                    }
                ).encode("utf-8"),
            ],
        )
        log.debug(
            f"{worker.name} - '{suuid}' job, sent ACK back to client '{client_address}'"
        )

        post_queue.task_done()


def _get(worker, get_queue, destroy_event, base_dir_jobs):
    """
    Thread to receive GET requests and retrieve results from the hard disk.

    Args:
        worker (Worker): The worker instance handling the request.
        get_queue (queue.Queue): The queue from which GET requests are received.
        destroy_event (threading.Event): Event to signal the thread to stop.
        base_dir_jobs (str): The base directory where job results are stored.
    """
    while not destroy_event.is_set():
        try:
            work = get_queue.get(block=True, timeout=0.1)
        except queue.Empty:
            continue

        client_address = work[0]
        suuid = work[2]
        rep_filename = reply_filename(suuid, base_dir_jobs)

        if os.path.exists(rep_filename):
            reply = loader(rep_filename)
        else:
            reply = [
                client_address,
                b"",
                suuid,
                b"400",
                json.dumps(
                    {
                        "worker": worker.name,
                        "uuid": suuid.decode("utf-8"),
                        "status": "JOB RESULTS NOT FOUND",
                        "service": worker.service.decode("utf-8"),
                    }
                ).encode("utf-8"),
            ]

        worker.send_to_broker(NFP.RESPONSE, reply)

        get_queue.task_done()


def _event(worker, event_queue, destroy_event):
    """
    Thread function to emit events to Clients.

    Args:
        worker (Worker): The worker instance that is emitting events.
        event_queue (queue.Queue): The queue from which events are retrieved.
        destroy_event (threading.Event): An event to signal the thread to stop.

    The function continuously retrieves events from the event_queue, processes them,
    and sends them to the broker until the destroy_event is set.
    """
    while not destroy_event.is_set():
        try:
            work = event_queue.get(block=True, timeout=0.1)
        except queue.Empty:
            continue

        client_address = work[0]
        suuid = work[1]
        task = work[2]
        timeout = work[3]
        data = work[4]

        event = [
            client_address,
            b"",
            suuid,
            b"200",
            json.dumps(
                {
                    "worker": worker.name,
                    "service": worker.service.decode("utf-8"),
                    "uuid": suuid.decode("utf-8"),
                    "task": task,
                    "timeout": timeout,
                    **data,
                }
            ).encode("utf-8"),
        ]

        worker.send_to_broker(NFP.EVENT, event)

        event_queue.task_done()


def close(delete_queue, queue_filename, destroy_event, base_dir_jobs):
    pass


def recv(worker, destroy_event):
    """
    Thread to process receive messages from broker.

    This function runs in a loop, polling the worker's broker socket for messages every second.
    When a message is received, it processes the message based on the command type and places
    it into the appropriate queue or handles it accordingly. If the keepaliver thread is not
    alive, it logs a warning and attempts to reconnect to the broker.

    Args:
        worker (Worker): The worker instance that contains the broker socket and queues.
        destroy_event (threading.Event): An event to signal the thread to stop.

    Commands:
        - NFP.POST: Places the message into the post_queue.
        - NFP.DELETE: Places the message into the delete_queue.
        - NFP.GET: Places the message into the get_queue.
        - NFP.KEEPALIVE: Processes a keepalive heartbeat.
        - NFP.DISCONNECT: Attempts to reconnect to the broker.
        - Other: Logs an invalid input message.
    """
    while not destroy_event.is_set():
        # Poll socket for messages every second
        try:
            items = worker.poller.poll(1000)
        except KeyboardInterrupt:
            break  # Interrupted
        if items:
            msg = worker.broker_socket.recv_multipart()
            log.debug(f"{worker.name} - received '{msg}'")
            empty = msg.pop(0)
            header = msg.pop(0)
            command = msg.pop(0)

            if command == NFP.POST:
                worker.post_queue.put(msg)
            elif command == NFP.DELETE:
                worker.delete_queue.put(msg)
            elif command == NFP.GET:
                worker.get_queue.put(msg)
            elif command == NFP.KEEPALIVE:
                worker.keepaliver.received_heartbeat([header] + msg)
            elif command == NFP.DISCONNECT:
                worker.reconnect_to_broker()
            else:
                log.debug(
                    f"{worker.name} - invalid input, header '{header}', command '{command}', message '{msg}'"
                )

        if not worker.keepaliver.is_alive():
            log.warning(f"{worker.name} - '{worker.broker}' broker keepalive expired")
            worker.reconnect_to_broker()


class NFPWorker:
    """
    NFPWorker class is responsible for managing worker operations,
    including connecting to a broker, handling jobs,  and maintaining
    keepalive connections. It interacts with the broker using ZeroMQ
    and manages job queues and events.

    Args:
        inventory (NorFabInventory): The inventory object containing base directory information.
        broker (str): The broker address.
        service (str): The service name.
        name (str): The name of the worker.
        exit_event: The event used to signal the worker to exit.
        log_level (str, optional): The logging level. Defaults to None.
        log_queue (object, optional): The logging queue. Defaults to None.
        multiplier (int, optional): The multiplier value. Defaults to 6.
        keepalive (int, optional): The keepalive interval in milliseconds. Defaults to 2500.

    Attributes:
        inventory (NorFabInventory): The inventory object.
        broker (str): The broker address.
        service (bytes): The service name encoded in UTF-8.
        name (str): The name of the worker.
        exit_event: The event used to signal the worker to exit.
        broker_socket: The broker socket, initialized to None.
        multiplier (int): The multiplier value.
        keepalive (int): The keepalive interval in milliseconds.
        socket_lock (threading.Lock): The lock used to protect the socket object.
        base_dir (str): The base directory for the worker.
        base_dir_jobs (str): The base directory for job files.
        destroy_event (threading.Event): The event used to signal the destruction of the worker.
        request_thread: The request thread, initialized to None.
        reply_thread: The reply thread, initialized to None.
        close_thread: The close thread, initialized to None.
        recv_thread: The receive thread, initialized to None.
        event_thread: The event thread, initialized to None.
        post_queue (queue.Queue): The queue for POST requests.
        get_queue (queue.Queue): The queue for GET requests.
        delete_queue (queue.Queue): The queue for DELETE requests.
        event_queue (queue.Queue): The queue for events.
        public_keys_dir (str): The directory for public keys.
        secret_keys_dir (str): The directory for private keys.
        ctx (zmq.Context): The ZeroMQ context.
        poller (zmq.Poller): The ZeroMQ poller.
        queue_filename (str): The filename for the job queue.
        queue_done_filename (str): The filename for the completed job queue.
        client (NFPClient): The NFP client instance.

    Methods:
        __init__(self, inventory, broker, service, name, exit_event, log_level=None, log_queue=None, multiplier=6, keepalive=2500):
            Initializes the NFPWorker instance with the provided parameters.
        setup_logging(self, log_queue, log_level):
            Configures logging for the worker.
        reconnect_to_broker(self):
            Connects or reconnects the worker to the broker.
        send_to_broker(self, command, msg=None):
            Sends a message to the broker with the specified command and optional message content.
        load_inventory(self):
            Loads the inventory from the broker for this worker name.
        worker_exit(self):
            Method to override in child classes with a set of actions to perform on exit call.
        get_inventory(self):
            Method to override in child classes to retrieve worker inventory.
        get_version(self):
            Method to override in child classes to retrieve worker version report.
        destroy(self, message=None):
            Cleans up and destroys the worker, stopping all threads and connections.
        is_url(self, url):
            Checks if the provided URL is in the expected format.
        fetch_file(self, url, raise_on_fail=False, read=True):
            Downloads a file from the broker File Sharing Service.
        fetch_jinja2(self, url):
            Recursively downloads a Jinja2 template and its included templates.
        event(self, data, **kwargs):
            Emits an event to the broker and saves it locally.
        job_details(self, uuid, data=True, result=True, events=True):
            Retrieves job details by UUID for completed jobs.
        job_list(self, pending=True, completed=True, task=None, last=None, client=None, uuid=None):
            Lists worker jobs, both completed and pending.
        work(self):
            Starts the worker's main loop, processing jobs from the queue.
    """

    keepaliver = None
    stats_reconnect_to_broker = 0

    def __init__(
        self,
        inventory: NorFabInventory,
        broker: str,
        service: str,
        name: str,
        exit_event: object,
        log_level: str = None,
        log_queue: object = None,
        multiplier: int = 6,
        keepalive: int = 2500,
    ):
        self.setup_logging(log_queue, log_level)
        self.inventory = inventory
        self.broker = broker
        self.service = service.encode("utf-8") if isinstance(service, str) else service
        self.name = name
        self.exit_event = exit_event
        self.broker_socket = None
        self.multiplier = multiplier
        self.keepalive = keepalive
        self.socket_lock = (
            threading.Lock()
        )  # used for keepalives to protect socket object

        # create base directories
        self.base_dir = os.path.join(
            self.inventory.base_dir, "__norfab__", "files", "worker", self.name
        )
        self.base_dir_jobs = os.path.join(self.base_dir, "jobs")
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.base_dir_jobs, exist_ok=True)

        # create events and queues
        self.destroy_event = threading.Event()
        self.request_thread = None
        self.reply_thread = None
        self.close_thread = None
        self.recv_thread = None
        self.event_thread = None

        self.post_queue = queue.Queue(maxsize=0)
        self.get_queue = queue.Queue(maxsize=0)
        self.delete_queue = queue.Queue(maxsize=0)
        self.event_queue = queue.Queue(maxsize=0)

        # generate certificates and create directories
        generate_certificates(
            self.base_dir,
            cert_name=self.name,
            broker_keys_dir=os.path.join(
                self.inventory.base_dir, "__norfab__", "files", "broker", "public_keys"
            ),
            inventory=self.inventory,
        )
        self.public_keys_dir = os.path.join(self.base_dir, "public_keys")
        self.secret_keys_dir = os.path.join(self.base_dir, "private_keys")

        self.ctx = zmq.Context()
        self.poller = zmq.Poller()
        self.reconnect_to_broker()

        # create queue file
        self.queue_filename = os.path.join(self.base_dir_jobs, f"{self.name}.queue.txt")
        if not os.path.exists(self.queue_filename):
            with open(self.queue_filename, "w") as f:
                pass
        self.queue_done_filename = os.path.join(
            self.base_dir_jobs, f"{self.name}.queue.done.txt"
        )
        if not os.path.exists(self.queue_done_filename):
            with open(self.queue_done_filename, "w") as f:
                pass

        self.client = NFPClient(
            self.inventory,
            self.broker,
            name=f"{self.name}-NFPClient",
            exit_event=self.exit_event,
        )

    def setup_logging(self, log_queue, log_level: str) -> None:
        """
        Configures logging for the worker.

        This method sets up the logging configuration using a provided log queue and log level.
        It updates the logging configuration dictionary with the given log queue and log level,
        and then applies the configuration using `logging.config.dictConfig`.

        Args:
            log_queue (queue.Queue): The queue to be used for logging.
            log_level (str): The logging level to be set. If None, the default level is used.
        """
        logging_config_producer["handlers"]["queue"]["queue"] = log_queue
        if log_level is not None:
            logging_config_producer["root"]["level"] = log_level
        logging.config.dictConfig(logging_config_producer)

    def reconnect_to_broker(self):
        """
        Connect or reconnect to the broker.

        This method handles the connection or reconnection process to the broker.
        It performs the following steps:

        1. If there is an existing broker socket, it sends a disconnect message,
           unregisters the socket from the poller, and closes the socket.
        2. Creates a new DEALER socket and sets its identity.
        3. Loads the client's secret and public keys for CURVE authentication.
        4. Loads the server's public key for CURVE authentication.
        5. Connects the socket to the broker.
        6. Registers the socket with the poller for incoming messages.
        7. Sends a READY message to the broker to register the service.
        8. Starts or restarts the keepalive mechanism to maintain the connection.
        9. Increments the reconnect statistics counter.
        10. Logs the successful registration to the broker.
        """
        if self.broker_socket:
            self.send_to_broker(NFP.DISCONNECT)
            self.poller.unregister(self.broker_socket)
            self.broker_socket.close()

        self.broker_socket = self.ctx.socket(zmq.DEALER)
        self.broker_socket.setsockopt_unicode(zmq.IDENTITY, self.name, "utf8")
        self.broker_socket.linger = 0

        # We need two certificates, one for the client and one for
        # the server. The client must know the server's public key
        # to make a CURVE connection.
        client_secret_file = os.path.join(
            self.secret_keys_dir, f"{self.name}.key_secret"
        )
        client_public, client_secret = zmq.auth.load_certificate(client_secret_file)
        self.broker_socket.curve_secretkey = client_secret
        self.broker_socket.curve_publickey = client_public

        # The client must know the server's public key to make a CURVE connection.
        server_public_file = os.path.join(self.public_keys_dir, "broker.key")
        server_public, _ = zmq.auth.load_certificate(server_public_file)
        self.broker_socket.curve_serverkey = server_public

        self.broker_socket.connect(self.broker)
        self.poller.register(self.broker_socket, zmq.POLLIN)

        # Register service with broker
        self.send_to_broker(NFP.READY)

        # start keepalives
        if self.keepaliver is not None:
            self.keepaliver.restart(self.broker_socket)
        else:
            self.keepaliver = KeepAliver(
                address=None,
                socket=self.broker_socket,
                multiplier=self.multiplier,
                keepalive=self.keepalive,
                exit_event=self.destroy_event,
                service=self.service,
                whoami=NFP.WORKER,
                name=self.name,
                socket_lock=self.socket_lock,
            )
            self.keepaliver.start()

        self.stats_reconnect_to_broker += 1
        log.info(
            f"{self.name} - registered to broker at '{self.broker}', "
            f"service '{self.service.decode('utf-8')}'"
        )

    def send_to_broker(self, command, msg: list = None):
        """
        Send a message to the broker.

        Parameters:
            command (str): The command to send to the broker. Must be one of NFP.READY, NFP.DISCONNECT, NFP.RESPONSE, or NFP.EVENT.
            msg (list, optional): The message to send. If not provided, a default message will be created based on the command.

        Logs:
            Logs an error if the command is unsupported.
            Logs a debug message with the message being sent.

        Thread Safety:
            This method is thread-safe and uses a lock to ensure that the broker socket is accessed by only one thread at a time.
        """
        if command == NFP.READY:
            msg = [b"", NFP.WORKER, NFP.READY, self.service]
        elif command == NFP.DISCONNECT:
            msg = [b"", NFP.WORKER, NFP.DISCONNECT, self.service]
        elif command == NFP.RESPONSE:
            msg = [b"", NFP.WORKER, NFP.RESPONSE] + msg
        elif command == NFP.EVENT:
            msg = [b"", NFP.WORKER, NFP.EVENT] + msg
        else:
            log.error(
                f"{self.name} - cannot send '{command}' to broker, command unsupported"
            )
            return

        log.debug(f"{self.name} - sending '{msg}'")

        with self.socket_lock:
            self.broker_socket.send_multipart(msg)

    def load_inventory(self):
        """
        Load inventory data from the broker for this worker.

        This function retrieves inventory data from the broker service using the worker's name.
        It logs the received inventory data and returns the results if available.

        Returns:
            dict: The inventory data results if available, otherwise an empty dictionary.
        """
        inventory_data = self.client.get(
            "sid.service.broker", "get_inventory", kwargs={"name": self.name}
        )

        log.debug(f"{self.name} - worker received invenotry data {inventory_data}")

        if inventory_data["results"]:
            return inventory_data["results"]
        else:
            return {}

    def worker_exit(self) -> None:
        """
        Method to override in child classes with a set of actions to perform on exit call.

        This method should be implemented by subclasses to define any cleanup or finalization
        tasks that need to be performed when the worker is exiting.
        """
        return None

    def get_inventory(self) -> Dict:
        """
        Retrieve the worker's inventory.

        This method should be overridden in child classes to provide the specific
        implementation for retrieving the inventory of a worker.

        Returns:
            Dict: A dictionary representing the worker's inventory.

        Raises:
            NotImplementedError: If the method is not overridden in a child class.
        """
        raise NotImplementedError

    def get_version(self) -> Dict:
        """
        Retrieve the version report of the worker.

        This method should be overridden in child classes to provide the specific
        version report of the worker.

        Returns:
            Dict: A dictionary containing the version information of the worker.

        Raises:
            NotImplementedError: If the method is not overridden in a child class.
        """
        raise NotImplementedError

    def destroy(self, message=None):
        """
        Cleanly shuts down the worker by performing the following steps:

        1. Calls the worker_exit method to handle any worker-specific exit procedures.
        2. Sets the destroy_event to signal that the worker is being destroyed.
        3. Calls the destroy method on the client to clean up client resources.
        4. Joins all the threads (request_thread, reply_thread, close_thread, event_thread, recv_thread) if they are not None, ensuring they have finished execution.
        5. Destroys the context with a linger period of 0 to immediately close all sockets.
        6. Stops the keepaliver to cease any keepalive signals.
        7. Logs an informational message indicating that the worker has been destroyed, including an optional message.

        Args:
            message (str, optional): An optional message to include in the log when the worker is destroyed.
        """
        self.worker_exit()
        self.destroy_event.set()
        self.client.destroy()

        # join all the threads
        if self.request_thread is not None:
            self.request_thread.join()
        if self.reply_thread is not None:
            self.reply_thread.join()
        if self.close_thread is not None:
            self.close_thread.join()
        if self.event_thread is not None:
            self.event_thread.join()
        if self.recv_thread:
            self.recv_thread.join()

        self.ctx.destroy(0)

        # stop keepalives
        self.keepaliver.stop()

        log.info(f"{self.name} - worker destroyed, message: '{message}'")

    def is_url(self, url: str) -> bool:
        """
        Check if the given string is a URL supported by NorFab File Service.

        Args:
            url (str): The URL to check.

        Returns:
            bool: True if the URL supported by NorFab File Service, False otherwise.
        """
        return any(str(url).startswith(k) for k in ["nf://"])

    def fetch_file(
        self, url: str, raise_on_fail: bool = False, read: bool = True
    ) -> str:
        """
        Function to download file from broker File Sharing Service

        Args:
            url: file location string in ``nf://<filepath>`` format
            raise_on_fail: raise FIleNotFoundError if download fails
            read: if True returns file content, return OS path to saved file otherwise

        Returns:
            str: File content if read is True, otherwise OS path to the saved file.

        Raises:
            FileNotFoundError: If raise_on_fail is True and the download fails.
        """
        status, file_content = self.client.fetch_file(url=url, read=read)
        msg = f"{self.name} - worker '{url}' fetch file failed with status '{status}'"

        if status == "200":
            return file_content
        elif raise_on_fail is True:
            raise FileNotFoundError(msg)
        else:
            log.error(msg)
            return None

    def fetch_jinja2(self, url: str) -> str:
        """
        Helper function to recursively download a Jinja2 template along with
        other templates referenced using "include" statements.

        Args:
            url (str): A URL in the format ``nf://file/path`` to download the file.

        Returns:
            str: The file path of the downloaded Jinja2 template.

        Raises:
            FileNotFoundError: If the file download fails.
            Exception: If Jinja2 template parsing fails.
        """
        filepath = self.fetch_file(url, read=False)
        if filepath is None:
            msg = f"{self.name} - file download failed '{url}'"
            raise FileNotFoundError(msg)

        # download Jinja2 template "include"-ed files
        content = self.fetch_file(url, read=True)
        j2env = Environment(loader="BaseLoader")
        try:
            parsed_content = j2env.parse(content)
        except Exception as e:
            msg = f"{self.name} - Jinja2 template parsing failed '{url}', error: '{e}'"
            raise Exception(msg)

        # run recursion on include statements
        for node in parsed_content.find_all(Include):
            include_file = node.template.value
            base_path = os.path.split(url)[0]
            self.fetch_jinja2(os.path.join(base_path, include_file))

        return filepath

    def event(self, data: Union[NorFabEvent, str], **kwargs) -> None:
        """
        Handles the creation and emission of an event.

        This method takes event data, processes it, and sends it to the event queue.
        It also saves the event data locally for future reference.

        Args:
            data (Union[NorFabEvent, str]): The event data, which can be either an instance of NorFabEvent or a string.
            **kwargs: Additional keyword arguments to be passed when creating a NorFabEvent instance if `data` is a string.

        Logs:
            Error: Logs an error message if the event data cannot be formed.
        """
        try:
            if not isinstance(data, NorFabEvent):
                data = NorFabEvent(message=data, **kwargs)
        except Exception as e:
            log.error(f"Failed to form event data, error {e}")
            return
        data = data.model_dump(exclude_none=True)
        # form event ZeroMQ payload
        event_item = [
            self.current_job["client_address"],
            self.current_job["juuid"],
            self.current_job["task"],
            self.current_job["timeout"],
            data,
        ]
        # emit event to the broker
        self.event_queue.put(event_item)
        # save event locally
        filename = event_filename(self.current_job["juuid"], self.base_dir_jobs)
        events = loader(filename) if os.path.exists(filename) else []
        events.append(event_item)
        dumper(events, filename)

    def job_details(
        self, uuid: str, data: bool = True, result: bool = True, events: bool = True
    ) -> Result:
        """
        Method to get job details by UUID for completed jobs.

        Args:
            uuid (str): The job UUID to return details for.
            data (bool): If True, return job data.
            result (bool): If True, return job result.
            events (bool): If True, return job events.

        Returns:
            Result: A Result object with the job details.
        """
        job = None
        with queue_file_lock:
            with open(self.queue_done_filename, "rb+") as f:
                for entry in f.readlines():
                    job_data, job_result, job_events = None, None, []
                    job_entry = entry.decode("utf-8").strip()
                    suuid, start, end = job_entry.split("--")  # {suuid}--start--end
                    if suuid != uuid:
                        continue
                    # load job request details
                    client_address, empty, juuid, job_data_bytes = loader(
                        request_filename(suuid, self.base_dir_jobs)
                    )
                    if data:
                        job_data = json.loads(job_data_bytes.decode("utf-8"))
                    # load job result details
                    if result:
                        rep_filename = reply_filename(suuid, self.base_dir_jobs)
                        if os.path.exists(rep_filename):
                            job_result = loader(rep_filename)
                            job_result = json.loads(job_result[-1].decode("utf-8"))
                            job_result = job_result[self.name]
                    # load event details
                    if events:
                        events_filename = event_filename(suuid, self.base_dir_jobs)
                        if os.path.exists(events_filename):
                            job_events = loader(events_filename)
                            job_events = [e[-1] for e in job_events]

                    job = {
                        "uuid": suuid,
                        "client": client_address.decode("utf-8"),
                        "received_timestamp": start,
                        "done_timestamp": end,
                        "status": "COMPLETED",
                        "job_data": job_data,
                        "job_result": job_result,
                        "job_events": job_events,
                    }

        if job:
            return Result(
                task=f"{self.name}:job_details",
                result=job,
            )
        else:
            raise FileNotFoundError(f"{self.name} - job with UUID '{uuid}' not found")

    def job_list(
        self,
        pending: bool = True,
        completed: bool = True,
        task: str = None,
        last: int = None,
        client: str = None,
        uuid: str = None,
    ) -> Result:
        """
        Method to list worker jobs completed and pending.

        Args:
            pending (bool): If True or None, return pending jobs. If False, skip pending jobs.
            completed (bool): If True or None, return completed jobs. If False, skip completed jobs.
            task (str, optional): If provided, return only jobs with this task name.
            last (int, optional): If provided, return only the last N completed and last N pending jobs.
            client (str, optional): If provided, return only jobs submitted by this client.
            uuid (str, optional): If provided, return only the job with this UUID.

        Returns:
            Result: Result object with a list of jobs.
        """
        job_pending = []
        # load pending jobs
        if pending is True:
            with queue_file_lock:
                with open(self.queue_filename, "rb+") as f:
                    for entry in f.readlines():
                        job_entry = entry.decode("utf-8").strip()
                        suuid, start = job_entry.split("--")  # {suuid}--start
                        if uuid and suuid != uuid:
                            continue
                        client_address, empty, juuid, data = loader(
                            request_filename(suuid, self.base_dir_jobs)
                        )
                        if client and client_address.decode("utf-8") != client:
                            continue
                        job_task = json.loads(data.decode("utf-8"))["task"]
                        # check if need to skip this job
                        if task and job_task != task:
                            continue
                        job_pending.append(
                            {
                                "uuid": suuid,
                                "client": client_address.decode("utf-8"),
                                "received_timestamp": start,
                                "done_timestamp": None,
                                "task": job_task,
                                "status": "PENDING",
                                "worker": self.name,
                                "service": self.service.decode("utf-8"),
                            }
                        )
        job_completed = []
        # load done jobs
        if completed is True:
            with queue_file_lock:
                with open(self.queue_done_filename, "rb+") as f:
                    for entry in f.readlines():
                        job_entry = entry.decode("utf-8").strip()
                        suuid, start, end = job_entry.split("--")  # {suuid}--start--end
                        if uuid and suuid != uuid:
                            continue
                        client_address, empty, juuid, data = loader(
                            request_filename(suuid, self.base_dir_jobs)
                        )
                        if client and client_address.decode("utf-8") != client:
                            continue
                        job_task = json.loads(data.decode("utf-8"))["task"]
                        # check if need to skip this job
                        if task and job_task != task:
                            continue
                        job_completed.append(
                            {
                                "uuid": suuid,
                                "client": client_address.decode("utf-8"),
                                "received_timestamp": start,
                                "done_timestamp": end,
                                "task": job_task,
                                "status": "COMPLETED",
                                "worker": self.name,
                                "service": self.service.decode("utf-8"),
                            }
                        )
        if last:
            return Result(
                task=f"{self.name}:job_list",
                result=job_completed[len(job_completed) - last :]
                + job_pending[len(job_pending) - last :],
            )
        else:
            return Result(
                task=f"{self.name}:job_list",
                result=job_completed + job_pending,
            )

    def work(self):
        """
        Starts multiple threads to handle different tasks and processes jobs in a
        loop until an exit or destroy event is set.

        Threads started:

        - request_thread: Handles posting requests.
        - reply_thread: Handles getting replies.
        - close_thread: Handles closing operations.
        - event_thread: Handles event processing.
        - recv_thread: Handles receiving data.

        Main work loop:

        - Continuously checks for jobs to process from a queue file.
        - Loads job data and executes the corresponding task.
        - Saves the result of the job to a reply file.
        - Marks the job as processed by moving it from the queue file to a queue done file.

        Ensures proper cleanup by calling the destroy method when exit or destroy events are set.
        """
        # Start threads
        self.request_thread = threading.Thread(
            target=_post,
            daemon=True,
            name=f"{self.name}_post_thread",
            args=(
                self,
                self.post_queue,
                self.queue_filename,
                self.destroy_event,
                self.base_dir_jobs,
            ),
        )
        self.request_thread.start()
        self.reply_thread = threading.Thread(
            target=_get,
            daemon=True,
            name=f"{self.name}_get_thread",
            args=(self, self.get_queue, self.destroy_event, self.base_dir_jobs),
        )
        self.reply_thread.start()
        self.close_thread = threading.Thread(
            target=close,
            daemon=True,
            name=f"{self.name}_close_thread",
            args=(
                self.delete_queue,
                self.queue_filename,
                self.destroy_event,
                self.base_dir_jobs,
            ),
        )
        self.close_thread.start()
        self.event_thread = threading.Thread(
            target=_event,
            daemon=True,
            name=f"{self.name}_event_thread",
            args=(self, self.event_queue, self.destroy_event),
        )
        self.event_thread.start()
        # start receive thread after other threads
        self.recv_thread = threading.Thread(
            target=recv,
            daemon=True,
            name=f"{self.name}_recv_thread",
            args=(
                self,
                self.destroy_event,
            ),
        )
        self.recv_thread.start()

        # start main work loop
        while not self.exit_event.is_set() and not self.destroy_event.is_set():
            # get some job to do
            with queue_file_lock:
                with open(self.queue_filename, "rb+") as f:
                    # get first UUID
                    for entry in f.readlines():
                        entry = entry.decode("utf-8").strip()
                        if entry:
                            break
                    else:
                        time.sleep(0.001)
                        continue

            # load job data
            suuid = entry.split("--")[0]  # {suuid}--start--

            log.debug(f"{self.name} - processing request {suuid}")

            client_address, empty, juuid, data = loader(
                request_filename(suuid, self.base_dir_jobs)
            )

            data = json.loads(data)
            task = data.pop("task")
            args = data.pop("args", [])
            kwargs = data.pop("kwargs", {})
            timeout = data.pop("timeout", 60)

            self.current_job = {
                "client_address": client_address,
                "juuid": juuid,
                "task": task,
                "timeout": timeout,
            }

            log.debug(
                f"{self.name} - doing task '{task}', timeout: '{timeout}', data: "
                f"'{data}', args: '{args}', kwargs: '{kwargs}', client: "
                f"'{client_address}', job uuid: '{juuid}'"
            )

            # run the actual job
            try:
                result = getattr(self, task)(*args, **kwargs)
                if not isinstance(result, Result):
                    raise TypeError(
                        f"{self.name} - task '{task}' did not return Result object, data: {data}, args: '{args}', "
                        f"kwargs: '{kwargs}', client: '{client_address}', job uuid: '{juuid}'"
                    )
                if not getattr(result, "task"):
                    result.task = f"{self.name}:{task}"
                if not getattr(result, "juuid"):
                    result.juuid = juuid.decode("utf-8")
            except Exception as e:
                result = Result(
                    task=f"{self.name}:{task}",
                    errors=[traceback.format_exc()],
                    messages=[f"Worker experienced error: '{e}'"],
                    failed=True,
                )
                log.error(
                    f"{self.name} - worker experienced error:\n{traceback.format_exc()}"
                )

            # save job results to reply file
            dumper(
                [
                    client_address,
                    b"",
                    suuid.encode("utf-8"),
                    b"200",
                    json.dumps({self.name: result.dictionary()}).encode("utf-8"),
                ],
                reply_filename(suuid, self.base_dir_jobs),
            )

            # mark job entry as processed - remove from queue file and save into queue done file
            with queue_file_lock:
                with open(self.queue_filename, "rb+") as qf:
                    with open(self.queue_done_filename, "rb+") as qdf:
                        qdf.seek(0, os.SEEK_END)  # go to the end
                        entries = qf.readlines()
                        qf.seek(0, os.SEEK_SET)  # go to the beginning
                        qf.truncate()  # empty file content
                        for entry in entries:
                            entry = entry.decode("utf-8").strip()
                            # save done entry to queue_done_filename
                            if entry.startswith(suuid):
                                entry = f"{entry}--{time.ctime()}\n".encode("utf-8")
                                qdf.write(entry)
                            # re-save remaining entries to queue_filename
                            else:
                                qf.write(f"{entry}\n".encode("utf-8"))

        # make sure to clean up
        self.destroy(
            f"{self.name} - exit event is set '{self.exit_event.is_set()}', "
            f"destroy event is set '{self.destroy_event.is_set()}'"
        )
