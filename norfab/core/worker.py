"""
## CUDOS

Inspired by Majordomo Protocol Worker API, ZeroMQ, Python version.

Original MDP/Worker spec 

Location: http://rfc.zeromq.org/spec:7.

Author: Min RK <benjaminrk@gmail.com>

Based on Java example by Arkadiusz Orzechowski
"""
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

from .zhelpers import dump
from . import NFP
from uuid import uuid4
from .client import NFPClient
from .keepalives import KeepAliver
from .security import generate_certificates
from jinja2 import Environment, FileSystemLoader
from jinja2.nodes import Include
from norfab.utils.loggingutils import setup_logging
from typing import Any, Callable, Dict, List, Optional, Union

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------------
# NORFAB Worker watchdog Object
# --------------------------------------------------------------------------------------------


class WorkerWatchDog(threading.Thread):
    """
    Class to monitor worker performance
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
        mem_usage = self.get_ram_usage()
        """Return RAM usage in Mbyte"""
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
        """Return RAM usage in Mbyte"""
        return self.worker_process.memory_info().rss / 1024000

    def run(self):
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
    Result of running individual tasks.


    Attributes/Arguments:

    :param changed: ``True`` if the task is changing the system
    :param result: Result of the task execution, see task's documentation for details
    :param failed: Whether the execution failed or not
    :param severity_level (logging.LEVEL): Severity level associated to the result of the execution
    :param errors: exception thrown during the execution of the task (if any)
    :param task: Task function name that produced the results
    :param messages: List of messages produced by the task
    :param juuid: Job UUID associated with the task
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
        return '{}: "{}"'.format(self.__class__.__name__, self.task)

    def __str__(self) -> str:
        if self.errors:
            return str("\n\n".join(self.errors))

        return str(self.result)

    def dictionary(self):
        """Method to serialize result as a dictionary"""
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
    with file_write_lock:
        with open(filename, "wb") as f:
            pickle.dump(data, f)


def loader(filename):
    with file_write_lock:
        with open(filename, "rb") as f:
            return pickle.load(f)


def request_filename(suuid: Union[str, bytes], base_dir_jobs: str):
    """Returns freshly allocated request filename for given UUID str"""
    suuid = suuid.decode("utf-8") if isinstance(suuid, bytes) else suuid
    return os.path.join(base_dir_jobs, f"{suuid}.req")


def reply_filename(suuid: Union[str, bytes], base_dir_jobs: str):
    """Returns freshly allocated reply filename for given UUID str"""
    suuid = suuid.decode("utf-8") if isinstance(suuid, bytes) else suuid
    return os.path.join(base_dir_jobs, f"{suuid}.rep")


def event_filename(suuid: Union[str, bytes], base_dir_jobs: str):
    """Returns freshly allocated event filename for given UUID str"""
    suuid = suuid.decode("utf-8") if isinstance(suuid, bytes) else suuid
    return os.path.join(base_dir_jobs, f"{suuid}.event")


def _post(worker, post_queue, queue_filename, destroy_event, base_dir_jobs):
    """Thread to receive POST requests and save them to hard disk"""
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
    """Thread to receive GET requests and retrieve results from the hard disk"""
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
    """Thread function to emit events to Clients"""
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
                    "timestamp": time.ctime(),
                    "task": task,
                    "data": data,
                    "timeout": timeout,
                }
            ).encode("utf-8"),
        ]

        worker.send_to_broker(NFP.EVENT, event)

        event_queue.task_done()


def close(delete_queue, queue_filename, destroy_event, base_dir_jobs):
    pass


def recv(worker, destroy_event):
    """Thread to process receive messages from broker."""
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
    :param broker: str, broker endpoint e.g. tcp://127.0.0.1:5555
    :param service: str, service name
    :param name: str, worker name
    :param exist_event: obj, threading event, if set signal worker to stop
    :param multiplier: int, number of keepalives lost before consider other party dead
    :param keepalive: int, keepalive interval in milliseconds
    """

    def __init__(
        self,
        broker: str,
        service: str,
        name: str,
        exit_event,
        log_level: str = "WARNING",
        log_queue: object = None,
        multiplier: int = 6,
        keepalive: int = 2500,
    ):
        setup_logging(queue=log_queue, log_level=log_level)
        self.log_level = log_level
        self.broker = broker
        self.service = service
        self.name = name
        self.exit_event = exit_event
        self.broker_socket = None
        self.socket_lock = (
            threading.Lock()
        )  # used for keepalives to protect socket object

        # create base directories
        self.base_dir = os.path.join(
            os.getcwd(), "__norfab__", "files", "worker", self.name
        )
        self.base_dir_jobs = os.path.join(self.base_dir, "jobs")
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.base_dir_jobs, exist_ok=True)

        # generate certificates and create directories
        generate_certificates(
            self.base_dir,
            cert_name=self.name,
            broker_keys_dir=os.path.join(
                os.getcwd(), "__norfab__", "files", "broker", "public_keys"
            ),
        )
        self.public_keys_dir = os.path.join(self.base_dir, "public_keys")
        self.secret_keys_dir = os.path.join(self.base_dir, "private_keys")

        self.ctx = zmq.Context()
        self.poller = zmq.Poller()
        self.reconnect_to_broker()

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

        self.keepaliver = KeepAliver(
            address=None,
            socket=self.broker_socket,
            multiplier=multiplier,
            keepalive=keepalive,
            exit_event=self.destroy_event,
            service=self.service,
            whoami=NFP.WORKER,
            name=self.name,
            socket_lock=self.socket_lock,
            log_level=self.log_level,
        )
        self.keepaliver.start()
        self.client = NFPClient(
            self.broker, name=f"{self.name}-NFPClient", exit_event=self.exit_event
        )

    def reconnect_to_broker(self):
        """Connect or reconnect to broker"""
        if self.broker_socket:
            self.send_to_broker(NFP.DISCONNECT)
            self.poller.unregister(self.broker_socket)
            self.broker_socket.close()

        self.broker_socket = self.ctx.socket(zmq.DEALER)

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

        self.broker_socket.setsockopt_unicode(zmq.IDENTITY, self.name, "utf8")
        self.broker_socket.linger = 0
        self.broker_socket.connect(self.broker)
        self.poller.register(self.broker_socket, zmq.POLLIN)

        # Register service with broker
        self.send_to_broker(NFP.READY)

        log.info(
            f"{self.name} - registered to broker at '{self.broker}', service '{self.service}'"
        )

    def send_to_broker(self, command, msg: list = None):
        """Send message to broker.

        If no msg is provided, creates one internally
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
        Function to load inventory from broker for this worker name.
        """
        inventory_data = self.client.get(
            "sid.service.broker", "get_inventory", kwargs={"name": self.name}
        )

        log.debug(f"{self.name} - worker received invenotry data {inventory_data}")

        if inventory_data["results"]:
            return json.loads(inventory_data["results"])
        else:
            return {}

    def worker_exit(self) -> None:
        """Method to override in child classes"""
        return

    def destroy(self, message=None):
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
        return any(str(url).startswith(k) for k in ["nf://"])

    def fetch_file(
        self, url: str, raise_on_fail: bool = False, read: bool = True
    ) -> str:
        """
        Function to download file from broker File Sharing Service

        :param url: file location string in ``nf://<filepath>`` format
        :param raise_on_fail: raise FIleNotFoundError if download fails
        :param read: if True returns file content, return OS path to saved file otherwise
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
        Helper function to recursively download Jinja2 template together with
        other templates referenced using "include" statements

        :param url: ``nf://file/path`` like URL to download file
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

    def event(self, data: Any = None) -> None:
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

        :param uuid: str, job UUID to return details for
        :param data: bool, if True return job data
        :param result: bool, if True return job result
        :param events: bool, if True return job events
        :return: Result object with job details
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

        :param pending: bool, if True or None return pending jobs, if
            False skip pending jobs
        :param completed: bool, if True or None return completed jobs,
            if False skip completed jobs
        :param task: str, if provided return only jobs with this task name
        :param last: int, if provided return only last N completed and
            last N pending jobs
        :param client: str, if provided return only jobs submitted by this client
        :param uuid: str, if provided return only job with this UUID
        :return: Result object with list of jobs
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
