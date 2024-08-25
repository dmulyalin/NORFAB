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
import threading
import queue
import os
import pickle

from .zhelpers import dump
from . import NFP
from uuid import uuid4
from .client import NFPClient
from .keepalives import KeepAliver

from typing import Any, Callable, Dict, List, Optional, Union

log = logging.getLogger(__name__)

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
    :param name: Task function name that produced the results
    """

    def __init__(
        self,
        result: Any = None,
        failed: bool = False,
        errors: Optional[List[str]] = None,
        name: str = None,
        messages: Optional[List[str]] = None,
    ) -> None:
        self.name = name
        self.result = result
        self.failed = failed
        self.errors = errors or []
        self.messages = messages or []

    def __repr__(self) -> str:
        return '{}: "{}"'.format(self.__class__.__name__, self.name)

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
            "name": self.name,
            "failed": self.failed,
            "errors": self.errors,
            "result": self.result,
            "messages": self.messages,
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
        multiplier: int = 6,
        keepalive: int = 2500,
    ):
        log.setLevel(log_level.upper())
        self.log_level = log_level
        self.broker = broker
        self.service = service
        self.name = name
        self.exit_event = exit_event
        self.broker_socket = None
        self.socket_lock = (
            threading.Lock()
        )  # used for keepalives to protect socket object
        self.base_dir = f"__norfab__/files/worker/{self.name}/"
        self.base_dir_jobs = os.path.join(self.base_dir, "jobs")

        self.ctx = zmq.Context()
        self.poller = zmq.Poller()
        self.reconnect_to_broker()

        self.destroy_event = threading.Event()
        self.request_thread = None
        self.reply_thread = None
        self.close_thread = None
        self.recv_thread = None

        self.post_queue = queue.Queue(maxsize=0)
        self.get_queue = queue.Queue(maxsize=0)
        self.delete_queue = queue.Queue(maxsize=0)

        # create queue file
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.base_dir_jobs, exist_ok=True)
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

        if inventory_data:
            return json.loads(inventory_data)
        else:
            return {}

    def destroy(self, message=None):
        self.destroy_event.set()
        self.client.destroy()

        # join all the threads
        if self.request_thread is not None:
            self.request_thread.join()
        if self.reply_thread is not None:
            self.reply_thread.join()
        if self.close_thread is not None:
            self.close_thread.join()
        if self.recv_thread:
            self.recv_thread.join()

        self.ctx.destroy(0)

        # stop keepalives
        self.keepaliver.stop()

        log.info(f"{self.name} - worker destroyed, message: '{message}'")

    def fetch_file(self, url: str):
        """
        Function to download file from broker File Sharing Service

        :param url: file location string in ``nf://<filepath>`` format
        """
        status, file_content = self.client.fetch_file(url=url, read=True)

        if status == "200":
            return file_content
        else:
            log.error(
                f"{self.name} - worker '{url}' fetch file failed with status '{status}'"
            )
            return None

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

            log.debug(
                f"{self.name} - doing task '{task}', data: {data}, args: '{args}', "
                f"kwargs: '{kwargs}', client: '{client_address}', job uuid: '{juuid}'"
            )

            # run the actual job
            try:
                result = getattr(self, task)(*args, **kwargs)
                if not isinstance(result, Result):
                    raise TypeError(
                        f"{self.name} - task '{task}' did not return Result object, data: {data}, args: '{args}', "
                        f"kwargs: '{kwargs}', client: '{client_address}', job uuid: '{juuid}'"
                    )
            except Exception as e:
                result = Result(
                    name=f"{self.name}:{task}",
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
        self.destroy()
