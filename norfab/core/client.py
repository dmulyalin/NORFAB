"""
## CUDOS

Inspired by Majordomo Protocol Client API, ZeroMQ, Python version.

Original MDP/Client spec

Location: http://rfc.zeromq.org/spec:7.

Author: Min RK <benjaminrk@gmail.com>

Based on Java example by Arkadiusz Orzechowski
"""

import logging
import zmq
import sys
import time
import json
import os
import threading
import queue
import hashlib
from uuid import uuid4  # random uuid

from .security import generate_certificates
from . import NFP
from .zhelpers import dump

from typing import Union, List

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------------
# NIRFAB client, credits to https://rfc.zeromq.org/spec/9/
# --------------------------------------------------------------------------------------------


def event_filename(suuid: str, events_dir: str):
    """Returns freshly allocated event filename for given UUID str"""
    suuid = suuid.decode("utf-8") if isinstance(suuid, bytes) else suuid
    return os.path.join(events_dir, f"{suuid}.json")


def recv(client):
    """Thread to process receive messages from broker."""
    while not client.exit_event.is_set():
        # Poll socket for messages every timeout interval
        try:
            items = client.poller.poll(1000)
        except KeyboardInterrupt:
            break  # Interrupted
        except:
            continue
        if items:
            msg = client.broker_socket.recv_multipart()
            log.debug(f"{client.name} - received '{msg}'")
            if msg[2] == NFP.EVENT:
                client.event_queue.put(msg)
                client.stats_recv_event_from_broker += 1
            else:
                client.recv_queue.put(msg)
                client.stats_recv_from_broker += 1


class NFPClient(object):
    """NORFAB Protocol Client API.

    :param broker: str, broker endpoint e.g. tcp://127.0.0.1:5555
    :param name: str, client name, default is ``NFPClient``
    """

    broker = None
    ctx = None
    broker_socket = None
    poller = None
    name = None
    stats_send_to_broker = 0
    stats_recv_from_broker = 0
    stats_reconnect_to_broker = 0
    stats_recv_event_from_broker = 0

    def __init__(
        self, broker, name, log_level="WARNING", exit_event=None, event_queue=None
    ):
        log.setLevel(log_level.upper())
        self.name = name
        self.zmq_name = f"{self.name}-{uuid4().hex}"
        self.broker = broker
        self.base_dir = os.path.join(
            os.getcwd(), "__norfab__", "files", "client", self.name
        )
        self.base_dir_jobs = os.path.join(self.base_dir, "jobs")
        self.events_dir = os.path.join(self.base_dir, "events")

        # create base directories
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.base_dir_jobs, exist_ok=True)
        os.makedirs(self.events_dir, exist_ok=True)

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

        # create queue file
        self.queue_filename = os.path.join(
            self.base_dir_jobs, f"{self.name}.jobsqueue.txt"
        )
        if not os.path.exists(self.queue_filename):
            with open(self.queue_filename, "w") as f:
                pass

        self.exit_event = exit_event or threading.Event()
        self.recv_queue = queue.Queue(maxsize=0)
        self.event_queue = event_queue or queue.Queue(maxsize=1000)

        # start receive thread
        self.recv_thread = threading.Thread(
            target=recv, daemon=True, name=f"{self.name}_recv_thread", args=(self,)
        ).start()

    def _make_workers(self, workers) -> bytes:
        """Helper function to convert workers target to bytes"""
        # transform workers string to bytes
        if isinstance(workers, str):
            workers = workers.encode("utf-8")
        # encode workers names list to list of bytes
        elif isinstance(workers, list):
            workers = json.dumps(workers).encode("utf-8")

        return workers

    def reconnect_to_broker(self):
        """Connect or reconnect to broker"""
        if self.broker_socket:
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

        self.broker_socket.setsockopt_unicode(zmq.IDENTITY, self.zmq_name, "utf8")
        self.broker_socket.linger = 0
        self.broker_socket.connect(self.broker)
        self.poller.register(self.broker_socket, zmq.POLLIN)
        log.debug(f"{self.name} - client connected to broker at '{self.broker}'")
        self.stats_reconnect_to_broker += 1

    def send_to_broker(self, command, service, workers, uuid, request):
        """Send message to broker."""
        if command == NFP.POST:
            msg = [b"", NFP.CLIENT, command, service, workers, uuid, request]
        elif command == NFP.GET:
            msg = [b"", NFP.CLIENT, command, service, workers, uuid, request]
        else:
            log.error(
                f"{self.name} - cannot send '{command}' to broker, command unsupported"
            )
            return

        log.debug(f"{self.name} - sending '{msg}'")

        self.broker_socket.send_multipart(msg)
        self.stats_send_to_broker += 1

    def rcv_from_broker(self, command, service, uuid):
        """Wait for response from broker."""
        retries = 3
        while retries > 0:
            # check if need to stop
            if self.exit_event.is_set():
                break
            try:
                msg = self.recv_queue.get(block=True, timeout=3)
                self.recv_queue.task_done()
            except queue.Empty:
                if retries:
                    log.warning(
                        f"{self.name} - '{uuid}:{service}:{command}' job, "
                        f"no reply from broker '{self.broker}', reconnecting"
                    )
                    self.reconnect_to_broker()
                retries -= 1
                continue

            (
                empty,
                reply_header,
                reply_command,
                reply_service,
                reply_uuid,
                reply_status,
                reply_task_result,
            ) = msg

            # find message from recv queue for given uuid
            if reply_uuid == uuid:
                assert (
                    reply_header == NFP.CLIENT
                ), f"Was expecting client header '{NFP.CLIENT}' received '{reply_header}'"
                assert (
                    reply_command == command
                ), f"Was expecting reply command '{command}' received '{reply_command}'"
                assert (
                    reply_service == service
                ), f"Was expecting reply from '{service}' but received reply from '{reply_service}' service"

                return reply_status, reply_task_result
            else:
                self.recv_queue.put(msg)
        else:
            log.error(
                f"{self.name} - '{uuid}:{service}:{command}' job, "
                f"client {retries} retries attempts exceeded"
            )
            return b"408", b'{"status": "Request Timeout"}'

    def post(
        self,
        service: str,
        task: str,
        args: list = None,
        kwargs: dict = None,
        workers: str = "all",
        uuid: hex = None,
        timeout: int = 600,
    ):
        """
        Send job request to broker.

        Return dictionary with ``status``, ``workers``, ``errors`` keys
        containing list of workers acknowledged POST request.
        """
        uuid = uuid or uuid4().hex
        args = args or []
        kwargs = kwargs or {}
        ret = {"status": b"200", "workers": [], "errors": []}

        if not isinstance(service, bytes):
            service = service.encode("utf-8")

        if not isinstance(uuid, bytes):
            uuid = uuid.encode("utf-8")

        workers = self._make_workers(workers)

        request = json.dumps(
            {"task": task, "kwargs": kwargs or {}, "args": args or []}
        ).encode("utf-8")

        # run POST response loop
        start_time = time.time()
        while timeout > time.time() - start_time:
            # check if need to stop
            if self.exit_event.is_set():
                return ret
            self.send_to_broker(
                NFP.POST, service, workers, uuid, request
            )  # 1 send POST to broker
            status, post_response = self.rcv_from_broker(
                NFP.RESPONSE, service, uuid
            )  # 2 receive RESPONSE from broker
            if status == b"202":  # 3 go over RESPONSE status and decide what to do
                break
            else:
                msg = f"{self.name} - '{uuid}' job, POST Request not accepted by broker '{post_response}'"
                log.error(msg)
                ret["errors"].append(msg)
                ret["status"] = status
                return ret
        else:
            msg = f"{self.name} - '{uuid}' job, broker POST Request Timeout"
            log.error(msg)
            ret["errors"].append(msg)
            ret["status"] = b"408"
            return ret

        # get a list of workers where job was dispatched to
        post_response = json.loads(post_response)
        workers_dispatched = set(post_response["workers"])
        log.debug(
            f"{self.name} - broker dispatched job '{uuid}' POST request to workers {workers_dispatched}"
        )

        # wait workers to ACK POSTed job
        start_time = time.time()
        workers_acked = set()
        while timeout > time.time() - start_time:
            # check if need to stop
            if self.exit_event.is_set():
                return ret
            status, response = self.rcv_from_broker(NFP.RESPONSE, service, uuid)
            response = json.loads(response)
            if status == b"202":  # ACCEPTED
                log.debug(
                    f"{self.name} - '{uuid}' job, acknowledged by worker '{response}'"
                )
                workers_acked.add(response["worker"])
                if workers_acked == workers_dispatched:
                    break
            else:
                msg = (
                    f"{self.name} - '{uuid}:{service}:{task}' job, "
                    f"unexpected POST request status '{status}', response '{response}'"
                )
                log.error(msg)
                ret["errors"].append(msg)
        else:
            msg = (
                f"{self.name} - '{uuid}' job, POST request timeout exceeded, these workers did not "
                f"acknowledge the job {workers_dispatched - workers_acked}"
            )
            log.error(msg)
            ret["errors"].append(msg)
            ret["status"] = b"408"

        ret["workers"] = list(workers_acked)
        ret["status"] = ret["status"].decode("utf-8")

        log.debug(f"{self.name} - '{uuid}' job POST request completed '{ret}'")

        return ret

    def get(
        self,
        service: str,
        task: str,
        args: list = None,
        kwargs: dict = None,
        workers: str = "all",
        uuid: hex = None,
        timeout: int = 600,
    ):
        """S
        end job reply message to broker requesting job results.

        :param service: mandatory, service name to target
        :param task: mandatory, service task name to run
        :param args: optional, list of position argument for the task
        :param kwargs: optional, dictionary of key-word arguments for the task
        :param workers: optional, workers to target - ``all``, ``any``, or
            list of workers names
        :param uuid: optional, unique job identifier
        :param timeout: optional, job timeout in seconds, for how long client
            waits for job result before giving up

        Returns dictionary of ``status``, ``results`` and ``errors`` keys,
        where ``results`` key is a dictionary keyed by workers' names, and
        ``errors`` is a list of error strings.
        """
        uuid = uuid or uuid4().hex
        args = args or []
        kwargs = kwargs or {}
        wkrs = {
            "requested": workers,
            "done": set(),
            "dispatched": set(),
            "pending": set(),
        }
        ret = {"status": b"200", "results": {}, "errors": [], "workers": wkrs}

        if not isinstance(service, bytes):
            service = service.encode("utf-8")

        if not isinstance(uuid, bytes):
            uuid = uuid.encode("utf-8")

        workers = self._make_workers(workers)

        request = json.dumps(
            {"task": task, "kwargs": kwargs or {}, "args": args or []}
        ).encode("utf-8")

        # run GET response loop
        start_time = time.time()
        while timeout > time.time() - start_time:
            # check if need to stop
            if self.exit_event.is_set():
                return None
            # dispatch GET request to workers
            self.send_to_broker(NFP.GET, service, workers, uuid, request)
            status, get_response = self.rcv_from_broker(NFP.RESPONSE, service, uuid)
            ret["status"] = status
            # received actual GET request results from broker e.g. MMI, SID or FSS services
            if status == b"200":
                ret["results"] = get_response.decode("utf-8")
                break
            # received DISPATCH response from broker
            if status != b"202":
                msg = f"{status}, {self.name} job '{uuid}' GET Request not accepted by broker '{get_response}'"
                log.error(msg)
                ret["errors"].append(msg)
                break
            get_response = json.loads(get_response)
            wkrs["dispatched"] = set(get_response["workers"])
            # collect GET responses from individual workers
            workers_responded = set()
            while timeout > time.time() - start_time:
                # check if need to stop
                if self.exit_event.is_set():
                    return None
                status, response = self.rcv_from_broker(NFP.RESPONSE, service, uuid)
                log.debug(
                    f"{self.name} - job '{uuid}' response from worker '{response}'"
                )
                response = json.loads(response)
                if status == b"200":  # OK
                    ret["results"].update(response)
                    log.debug(
                        f"{self.name} - job '{uuid}' results returned by worker '{response}'"
                    )
                    for w in response.keys():
                        wkrs["done"].add(w)
                        workers_responded.add(w)
                        if w in wkrs["pending"]:
                            wkrs["pending"].remove(w)
                    if wkrs["done"] == wkrs["dispatched"]:
                        break
                elif status == b"300":  # PENDING
                    # set status to pending if at least one worker is pending
                    ret["status"] = b"300"
                    wkrs["pending"].add(response["worker"])
                    workers_responded.add(response["worker"])
                else:
                    if response.get("worker"):
                        workers_responded.add(response["worker"])
                    msg = (
                        f"{self.name} - '{uuid}:{service}:{task}' job, "
                        f"unexpected GET Response status '{status}', response '{response}'"
                    )
                    log.error(msg)
                    ret["errors"].append(msg)
                if workers_responded == wkrs["dispatched"]:
                    break
            if wkrs["done"] == wkrs["dispatched"]:
                break
            time.sleep(0.2)
        else:
            msg = f"{self.name} - '{uuid}' job, broker {timeout}s GET request timeout expired"
            log.error(msg)
            ret["errors"].append(msg)
            ret["status"] = b"408"

        ret["status"] = ret["status"].decode("utf-8")

        return ret

    def get_iter(
        self,
        service: str,
        task: str,
        args: list = None,
        kwargs: dict = None,
        workers: str = "all",
        uuid: hex = None,
        timeout: int = 600,
    ):
        """Send job reply message to broker requesting job results."""
        uuid = uuid or uuid4().hex
        args = args or []
        kwargs = kwargs or {}

        if not isinstance(service, bytes):
            service = service.encode("utf-8")

        if not isinstance(uuid, bytes):
            uuid = uuid.encode("utf-8")

        workers = self._make_workers(workers)

        request = json.dumps(
            {"task": task, "kwargs": kwargs or {}, "args": args or []}
        ).encode("utf-8")

        # run GET response loop
        start_time = time.time()
        workers_done = set()
        while timeout > time.time() - start_time:
            # check if need to stop
            if self.exit_event.is_set():
                break
            # dispatch GET request to workers
            self.send_to_broker(NFP.GET, service, workers, uuid, request)
            status, get_response = self.rcv_from_broker(NFP.RESPONSE, service, uuid)
            # received DISPATCH response from broker
            if status != b"202":
                msg = f"{status}, {self.name} job '{uuid}' GET Request not accepted by broker '{get_response}'"
                log.error(msg)
                break
            get_response = json.loads(get_response)
            workers_dispatched = set(get_response["workers"])
            # collect GET responses from workers
            workers_responded = set()
            while timeout > time.time() - start_time:
                # check if need to stop
                if self.exit_event.is_set():
                    break
                status, response = self.rcv_from_broker(NFP.RESPONSE, service, uuid)
                log.debug(
                    f"{self.name} - job '{uuid}' response from worker '{response}'"
                )
                response = json.loads(response)
                if status == b"200":  # OK
                    log.debug(
                        f"{self.name} - job '{uuid}' results returned by worker '{response}'"
                    )
                    yield response
                    for w in response.keys():
                        workers_done.add(w)
                        workers_responded.add(w)
                    if workers_done == workers_dispatched:
                        break
                elif status == b"300":  # PENDING
                    workers_responded.add(response["worker"])
                else:
                    msg = f"{self.name} - unexpected GET Response status '{status}', response '{response}'"
                    log.error(msg)
                    ret["errors"].append(msg)
                if workers_responded == workers_dispatched:
                    break
            if workers_done == workers_dispatched:
                break
            time.sleep(0.2)
        else:
            msg = f"408, {self.name} job '{uuid}' broker GET Request Timeout"
            log.error(msg)

    def fetch_file(
        self,
        url: str,
        destination: str = None,
        chunk_size: int = 250000,
        pipiline: int = 10,
        timeout: int = 600,
        read: bool = False,
    ):
        """
        Function to download file from Broker File Sharing Service.

        :param url: (str), path to file relative to ``base_dir``
        :param destination: (str), if provided destination to save file,
            returns file content otherwise
        """
        uuid = str(uuid4().hex).encode("utf-8")
        total = 0  # Total bytes received
        chunks = 0  # Total chunks received
        offset = 0  # Offset of next chunk request
        credit = pipiline  # Up to PIPELINE chunks in transit
        service = b"fss.service.broker"
        workers = b"any"
        reply = ""
        status = "200"
        downloaded = False
        md5hash = None

        # define file destination
        if destination is None:
            destination = os.path.join(
                self.base_dir, "fetchedfiles", *os.path.split(url.replace("nf://", ""))
            )

        # make sure all destination directories exist
        os.makedirs(os.path.split(destination)[0], exist_ok=True)

        # get file details
        request = json.dumps({"task": "file_details", "kwargs": {"url": url}}).encode(
            "utf-8"
        )
        self.send_to_broker(NFP.GET, service, workers, uuid, request)
        rcv_status, file_details = self.rcv_from_broker(NFP.RESPONSE, service, uuid)
        file_details = json.loads(file_details)

        # check if file already downloaded
        if os.path.isfile(destination):
            file_hash = hashlib.md5()
            with open(destination, "rb") as f:
                chunk = f.read(8192)
                while chunk:
                    file_hash.update(chunk)
                    chunk = f.read(8192)
            md5hash = file_hash.hexdigest()
            downloaded = md5hash == file_details["md5hash"]
            log.debug(f"{self.name} - file already downloaded, nothing to do")

        # fetch file content from broker and save to local file
        if file_details["exists"] is True and downloaded is False:
            file_hash = hashlib.md5()
            with open(destination, "wb") as dst_file:
                start_time = time.time()
                while timeout > time.time() - start_time:
                    # check if need to stop
                    if self.exit_event.is_set():
                        return "400", ""
                    # ask for chunks
                    while credit:
                        request = json.dumps(
                            {
                                "task": "fetch_file",
                                "kwargs": {
                                    "offset": offset,
                                    "chunk_size": chunk_size,
                                    "url": url,
                                },
                            }
                        ).encode("utf-8")
                        self.send_to_broker(NFP.GET, service, workers, uuid, request)
                        offset += chunk_size
                        credit -= 1
                    # receive chunks from broker
                    status, chunk = self.rcv_from_broker(NFP.RESPONSE, service, uuid)
                    log.debug(
                        f"{self.name} - status '{status}', chunk '{chunks}', downloaded '{total}'"
                    )
                    dst_file.write(chunk)
                    file_hash.update(chunk)
                    chunks += 1
                    credit += 1
                    size = len(chunk)
                    total += size
                    if size < chunk_size:
                        break  # Last chunk received; exit
                else:
                    reply = "File download failed - timeout"
                    status = "408"
            # verify md5hash
            md5hash = file_hash.hexdigest()
        elif file_details["exists"] is False:
            reply = "File download failed - file not found"
            status = "404"

        # decide on what to reply and status
        if file_details["exists"] is not True:
            reply = reply
        elif md5hash != file_details["md5hash"]:
            reply = "File download failed - MD5 hash mismatch"
            status = "417"
        elif read:
            with open(destination, "r", encoding="utf-8") as f:
                reply = f.read()
        else:
            reply = destination
        # decode status
        if isinstance(status, bytes):
            status = status.decode("utf-8")

        return status, reply

    def run_job(
        self,
        service: str,
        task: str,
        uuid: str = None,
        args: list = None,
        kwargs: dict = None,
        workers: str = "all",
        timeout: int = 600,
        retry=10,
    ):
        """
        Run job and return results produced by workers.

        :param service: str, service name to send request to
        :param task: str, task name to run for given service
        :param uuid: (str) Job ID to use
        :param args: list, task arguments
        :param kwargs: dict, task key-word arguments
        :param workers: str or list, worker names to target
        :param timeout: overall job timeout in seconds
        :param retry: number of times to try and GET job results
        """
        uuid = uuid or uuid4().hex
        start_time = int(time.time())

        # POST job to workers
        post_result = self.post(service, task, args, kwargs, workers, uuid, timeout)
        if post_result["status"] != "200":
            log.error(
                f"{self.name}:run_job - {service}:{task} POST status "
                f"to '{workers}' workers is not 200 - '{post_result}'"
            )
            return None

        remaining_timeout = timeout - (time.time() - start_time)
        get_timeout = remaining_timeout / retry

        # GET job results
        while retry:
            get = self.get(
                service, task, [], {}, post_result["workers"], uuid, get_timeout
            )
            if self.exit_event.is_set():
                break
            elif get["status"] == "300":  # PENDING
                retry -= 1
                log.debug(
                    f"{self.name}:run_job - {service}:{task}:{uuid} GET "
                    f"results pending, keep waiting"
                )
                continue
            elif get["status"] == "408":  # TIMEOUT
                retry -= 1
                log.debug(
                    f"{self.name}:run_job - {service}:{task}:{uuid} GET "
                    f"results {get_timeout}s timeout expired, keep waiting"
                )
                continue
            elif get["status"] in ["200", "202"]:  # OK
                return get["results"]
            else:
                log.error(
                    f"{self.name}:run_job - {service}:{task}:{uuid} "
                    f"stopping, GET returned unexpected results - '{get}'"
                )
                return None

    def run_job_iter(
        self,
        service: str,
        task: str,
        uuid: str = None,
        args: list = None,
        kwargs: dict = None,
        workers: str = "all",
        timeout: int = 600,
    ):
        """
        Iter run_job allows to return job results from workers progressively
        as they are responded, rather than waiting for workers to respond first.
        This should allow to client an interactive experience for the user where
        job results would be presented as soon as they are available.

        :param service: str, service name to send request to
        :param task: str, task name to run for given service
        :param uuid: (str) Job ID to use
        :param args: list, task arguments
        :param kwargs: dict, task key-word arguments
        :param workers: str or list, worker names to target
        """
        uuid = uuid or uuid4().hex

        # POST job to workers
        post_result = self.post(service, task, args, kwargs, workers, uuid, timeout)

        # GET job results
        for result in self.get_iter(
            service, task, [], {}, post_result["workers"], uuid, timeout
        ):
            yield result

    def destroy(self):
        log.info(f"{self.name} - client interrupt received, killing client")
        self.exit_event.set()
        self.ctx.destroy()
