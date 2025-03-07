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
from norfab.core.inventory import NorFabInventory
from typing import Union, List, Callable, Any

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------------
# NIRFAB client, credits to https://rfc.zeromq.org/spec/9/
# --------------------------------------------------------------------------------------------


def event_filename(suuid: str, events_dir: str):
    """
    Returns a freshly allocated event filename for the given UUID string.

    Args:
        suuid (str): The UUID string for which to generate the event filename.
                     If the input is a bytes object, it will be decoded to a string.
        events_dir (str): The directory where the event file will be stored.

    Returns:
        str: The full path to the event file, with the filename in the format '{suuid}.json'.
    """
    suuid = suuid.decode("utf-8") if isinstance(suuid, bytes) else suuid
    return os.path.join(events_dir, f"{suuid}.json")


def recv(client):
    """
    Thread to process and handle received messages from a broker.

    This function continuously polls the client's broker socket for messages
    until the client's exit event is set. It processes the received messages
    and places them into the appropriate queues based on the message type.

    Args:
        client (object): The client instance containing the broker socket,
                         poller, and queues for handling messages.

    Raises:
        KeyboardInterrupt: If the polling is interrupted by a keyboard interrupt.
    """
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
    """
    NFPClient is a client class for interacting with a broker using ZeroMQ for messaging.
    It handles sending and receiving messages, managing connections, and performing tasks.

    Attributes:
        broker (str): The broker address.
        ctx (zmq.Context): The ZeroMQ context.
        broker_socket (zmq.Socket): The ZeroMQ socket for communication with the broker.
        poller (zmq.Poller): The ZeroMQ poller for managing socket events.
        name (str): The name of the client.
        stats_send_to_broker (int): Counter for messages sent to the broker.
        stats_recv_from_broker (int): Counter for messages received from the broker.
        stats_reconnect_to_broker (int): Counter for reconnections to the broker.
        stats_recv_event_from_broker (int): Counter for events received from the broker.
        client_private_key_file (str): Path to the client's private key file.
        broker_public_key_file (str): Path to the broker's public key file.

    Methods:
        __init__(inventory, broker, name, exit_event=None, event_queue=None):
            Initializes the NFPClient instance with the given parameters.
        _make_workers(workers) -> bytes:
            Helper function to convert workers target to bytes.
        reconnect_to_broker():
            Connects or reconnects to the broker.
        send_to_broker(command, service, workers, uuid, request):
            Sends a message to the broker.
        rcv_from_broker(command, service, uuid):
            Waits for a response from the broker.
        post(service, task, args=None, kwargs=None, workers="all", uuid=None, timeout=600):
            Sends a job request to the broker and returns the result.
        get(service, task=None, args=None, kwargs=None, workers="all", uuid=None, timeout=600):
            Sends a job reply message to the broker requesting job results.
        get_iter(service, task, args=None, kwargs=None, workers="all", uuid=None, timeout=600):
            Sends a job reply message to the broker requesting job results and yields results iteratively.
        fetch_file(url, destination=None, chunk_size=250000, pipiline=10, timeout=600, read=False):
            Downloads a file from the Broker File Sharing Service.
        run_job(service, task, uuid=None, args=None, kwargs=None, workers="all", timeout=600, retry=10):
            Runs a job and returns results produced by workers.
        run_job_iter(service, task, uuid=None, args=None, kwargs=None, workers="all", timeout=600):
            Runs a job and yields results produced by workers iteratively.
        destroy():
            Cleans up and destroys the client instance.

    Args:
        inventory (NorFabInventory): The inventory object containing base directory information.
        broker: The broker object for communication.
        name (str): The name of the client.
        exit_event (threading.Event, optional): An event to signal client exit. Defaults to None.
        event_queue (queue.Queue, optional): A queue for handling events. Defaults to None.
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
    client_private_key_file = None
    broker_public_key_file = None

    def __init__(
        self,
        inventory: NorFabInventory,
        broker,
        name,
        exit_event=None,
        event_queue=None,
    ):
        self.inventory = inventory
        self.name = name
        self.zmq_name = f"{self.name}-{uuid4().hex}"
        self.broker = broker
        self.base_dir = os.path.join(
            self.inventory.base_dir, "__norfab__", "files", "client", self.name
        )
        self.jobs_dir = os.path.join(self.base_dir, "jobs")
        self.events_dir = os.path.join(self.base_dir, "events")
        self.running_job = None

        # create base directories
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.jobs_dir, exist_ok=True)
        os.makedirs(self.events_dir, exist_ok=True)

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
        self.private_keys_dir = os.path.join(self.base_dir, "private_keys")

        self.ctx = zmq.Context()
        self.poller = zmq.Poller()
        self.reconnect_to_broker()

        # create queue file
        self.queue_filename = os.path.join(self.jobs_dir, f"{self.name}.jobsqueue.txt")
        if not os.path.exists(self.queue_filename):
            with open(self.queue_filename, "w") as f:
                pass

        self.exit_event = threading.Event() if exit_event is None else exit_event
        self.destroy_event = (
            threading.Event()
        )  # destroy event, used by worker to stop its client
        self.recv_queue = queue.Queue(maxsize=0)
        self.event_queue = event_queue or queue.Queue(maxsize=1000)

        # start receive thread
        self.recv_thread = threading.Thread(
            target=recv, daemon=True, name=f"{self.name}_recv_thread", args=(self,)
        )
        self.recv_thread.start()

    def _make_workers(self, workers: Union[str, list]) -> bytes:
        """
        Helper function to convert workers target to bytes.

        This function takes a workers target, which can be either a string or a list,
        and converts it to a bytes object. If the input is a string, it is encoded
        using UTF-8. If the input is a list, it is first converted to a JSON string
        and then encoded using UTF-8.

        Args:
            workers (Union[str, list]): The workers target to be converted to bytes.

        Returns:
            bytes: The workers target converted to bytes.
        """
        # transform workers string to bytes
        if isinstance(workers, str):
            workers = workers.encode("utf-8")
        # encode workers names list to list of bytes
        elif isinstance(workers, list):
            workers = json.dumps(workers).encode("utf-8")

        return workers

    def reconnect_to_broker(self):
        """
        Connect or reconnect to the broker.

        This method handles the connection or reconnection to the broker by:

        - Closing the existing broker socket if it exists.
        - Creating a new DEALER socket.
        - Setting the socket options including the identity and linger.
        - Loading the client's private and public keys for CURVE encryption.
        - Loading the broker's public key for CURVE encryption.
        - Connecting the socket to the broker.
        - Registering the socket with the poller for incoming messages.
        - Logging the connection status.
        - Incrementing the reconnect statistics counter.
        """
        if self.broker_socket:
            self.poller.unregister(self.broker_socket)
            self.broker_socket.close()

        self.broker_socket = self.ctx.socket(zmq.DEALER)
        self.broker_socket.setsockopt_unicode(zmq.IDENTITY, self.zmq_name, "utf8")
        self.broker_socket.linger = 0

        # We need two certificates, one for the client and one for
        # the server. The client must know the server's public key
        # to make a CURVE connection.
        self.client_private_key_file = os.path.join(
            self.private_keys_dir, f"{self.name}.key_secret"
        )
        client_public, client_secret = zmq.auth.load_certificate(
            self.client_private_key_file
        )
        self.broker_socket.curve_secretkey = client_secret
        self.broker_socket.curve_publickey = client_public

        # The client must know the server's public key to make a CURVE connection.
        self.broker_public_key_file = os.path.join(self.public_keys_dir, "broker.key")
        server_public, _ = zmq.auth.load_certificate(self.broker_public_key_file)
        self.broker_socket.curve_serverkey = server_public

        self.broker_socket.connect(self.broker)
        self.poller.register(self.broker_socket, zmq.POLLIN)
        log.debug(f"{self.name} - client connected to broker at '{self.broker}'")
        self.stats_reconnect_to_broker += 1

    def send_to_broker(self, command, service, workers, uuid, request):
        """
        Sends a command to the broker.

        Args:
            command (str): The command to send (e.g., NFP.POST, NFP.GET).
            service (str): The service to which the command is related.
            workers (str): The workers involved in the command.
            uuid (str): The unique identifier for the request.
            request (str): The request payload to be sent.
        """
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
        """
        Wait for a response from the broker for a given command, service, and uuid.

        Args:
            command (str): The command sent to the broker.
            service (str): The service to which the command is sent.
            uuid (str): The unique identifier for the request.

        Returns:
            tuple: A tuple containing the reply status and the reply task result.

        Raises:
            AssertionError: If the reply header, command, or service does not match the expected values.
        """
        retries = 3
        while retries > 0:
            # check if need to stop
            if self.exit_event.is_set() or self.destroy_event.is_set():
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
    ) -> dict:
        """
        Send a job POST request to the broker.

        Args:
            service (str): The name of the service to send the request to.
            task (str): The task to be executed by the service.
            args (list, optional): A list of positional arguments to pass to the task. Defaults to None.
            kwargs (dict, optional): A dictionary of keyword arguments to pass to the task. Defaults to None.
            workers (str, optional): The workers to handle the task. Defaults to "all".
            uuid (hex, optional): The unique identifier for the job. Defaults to None.
            timeout (int, optional): The timeout for the request in seconds. Defaults to 600.

        Returns:
            A dictionary containing the ``status``, ``workers``, ``errors``, and ``uuid`` keys of the request:

                - ``status``: Status of the request.
                - ``uuid``: Unique identifier of the request.
                - ``errors``: List of error strings.
                - ``workers``: A list of worker names who acknowledged this POST request.
        """
        uuid = uuid or uuid4().hex
        args = args or []
        kwargs = kwargs or {}
        ret = {"status": b"200", "workers": [], "errors": [], "uuid": uuid}

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
            if self.exit_event.is_set() or self.destroy_event.is_set():
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
            if self.exit_event.is_set() or self.destroy_event.is_set():
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
        task: str = None,
        args: list = None,
        kwargs: dict = None,
        workers: str = "all",
        uuid: hex = None,
        timeout: int = 600,
    ) -> dict:
        """
        Send job GET request message to broker requesting job results.

        Args:
            task (str): service task name to run
            args (list): list of positional arguments for the task
            kwargs (dict): dictionary of keyword arguments for the task
            workers (list): workers to target - ``all``, ``any``, or list of workers' names
            timeout (int): job timeout in seconds, for how long client waits for job result before giving up

        Returns:
            Dictionary containing ``status``, ``results``, ``errors``, and ``workers`` keys:

                - ``status``: Status of the request.
                - ``results``: Dictionary keyed by workers' names containing the results.
                - ``errors``: List of error strings.
                - ``workers``: Dictionary containing worker states (requested, done, dispatched, pending).
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
            if self.exit_event.is_set() or self.destroy_event.is_set():
                return None
            # dispatch GET request to workers
            self.send_to_broker(NFP.GET, service, workers, uuid, request)
            status, get_response = self.rcv_from_broker(NFP.RESPONSE, service, uuid)
            ret["status"] = status
            # received actual GET request results from broker e.g. MMI, SID or FSS services
            if status == b"200":
                ret["results"] = json.loads(get_response.decode("utf-8"))
                break
            # received DISPATCH response from broker
            if status != b"202":
                msg = f"{status}, {self.name} job '{uuid}' GET Request not accepted by broker '{get_response}'"
                log.error(msg)
                ret["status"] = status
                ret["errors"].append(msg)
                break
            get_response = json.loads(get_response)
            wkrs["dispatched"] = set(get_response["workers"])
            # collect GET responses from individual workers
            workers_responded = set()
            while timeout > time.time() - start_time:
                # check if need to stop
                if self.exit_event.is_set() or self.destroy_event.is_set():
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
            log.info(msg)
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
    ) -> dict:
        """
        Send job reply message to broker requesting job results.

        Args:
            service (str): The service name.
            task (str): The task name.
            args (list, optional): The list of arguments for the task. Defaults to None.
            kwargs (dict, optional): The dictionary of keyword arguments for the task. Defaults to None.
            workers (str, optional): The workers to dispatch the task to. Defaults to "all".
            uuid (hex, optional): The unique identifier for the job. Defaults to None.
            timeout (int, optional): The timeout duration in seconds. Defaults to 600.

        Yields:
            dict: The response from the worker containing the results of the task.

        Raises:
            Exception: If the job request is not accepted by the broker or if there is an unexpected response status.

        Notes:
            - The method sends a GET request to the broker and waits for responses from the workers.
            - If the timeout is reached or an exit event is set, the method stops waiting for responses.
            - The method logs errors and debug information during the process.
        """
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
            if self.exit_event.is_set() or self.destroy_event.is_set():
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
                if self.exit_event.is_set() or self.destroy_event.is_set():
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
        Fetches a file from a given URL and saves it to a specified destination.

        Parameters:
            url (str): The URL of the file to be fetched.
            destination (str, optional): The local path where the file should be saved. If None, a default path is used.
            chunk_size (int, optional): The size of each chunk to be fetched. Default is 250000 bytes.
            pipiline (int, optional): The number of chunks to be fetched in parallel. Default is 10.
            timeout (int, optional): The maximum time (in seconds) to wait for the file to be fetched. Default is 600 seconds.
            read (bool, optional): If True, the file content is read and returned. If False, the file path is returned. Default is False.

        Returns:
            tuple: A tuple containing the status code (str) and the reply (str). The reply can be the file content, file path, or an error message.

        Raises:
            Exception: If there is an error in fetching the file or if the file's MD5 hash does not match the expected hash.
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
                    if self.exit_event.is_set() or self.destroy_event.is_set():
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
        Run a job on the specified service and task, with optional arguments, timeout and retry settings.

        Args:
            service (str): The name of the service to run the job on.
            task (str): The task to be executed.
            uuid (str, optional): A unique identifier for the job. If not provided, a new UUID will be generated. Defaults to None.
            args (list, optional): A list of positional arguments to pass to the task. Defaults to None.
            kwargs (dict, optional): A dictionary of keyword arguments to pass to the task. Defaults to None.
            workers (str, optional): The workers to run the job on. Defaults to "all".
            timeout (int, optional): The maximum time in seconds to wait for the job to complete. Defaults to 600.
            retry (int, optional): The number of times to retry getting the job results. Defaults to 10.

        Returns:
            Any: The result of the job if successful, or None if the job failed or timed out.

        Raises:
            Exception: If the POST request to start the job fails or if an unexpected status is returned during the GET request.
        """
        self.running_job = True
        uuid = uuid or uuid4().hex
        start_time = int(time.time())
        ret = None

        # POST job to workers
        post_result = self.post(service, task, args, kwargs, workers, uuid, timeout)
        if post_result["status"] != "200":
            log.error(
                f"{self.name}:run_job - {service}:{task} POST status "
                f"to '{workers}' workers is not 200 - '{post_result}'"
            )
            self.running_job = False
            return ret

        remaining_timeout = timeout - (time.time() - start_time)
        get_timeout = remaining_timeout / retry

        # GET job results
        while retry:
            get = self.get(
                service, task, [], {}, post_result["workers"], uuid, get_timeout
            )
            if self.exit_event.is_set() or self.destroy_event.is_set():
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
                ret = get["results"]
                break
            else:
                log.error(
                    f"{self.name}:run_job - {service}:{task}:{uuid} "
                    f"stopping, GET returned unexpected results - '{get}'"
                )
                break
        else:
            log.error(
                f"{self.name}:run_job - {service}:{task}:{uuid} "
                f"retry exceeded, GET returned no results, timeout {timeout}s"
            )
        self.running_job = False
        return ret

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
        Run a job on the specified service and task, yielding results as they are received.

        Args:
            service (str): The name of the service to run the job on.
            task (str): The name of the task to run.
            uuid (str, optional): A unique identifier for the job. If not provided, a new UUID will be generated. Defaults to None.
            args (list, optional): A list of positional arguments to pass to the task. Defaults to None.
            kwargs (dict, optional): A dictionary of keyword arguments to pass to the task. Defaults to None.
            workers (str, optional): The workers to run the job on. Defaults to "all".
            timeout (int, optional): The timeout for the job in seconds. Defaults to 600.

        Yields:
            result: The result of the job as it is received from the workers.
        """
        self.running_job = True
        uuid = uuid or uuid4().hex

        # POST job to workers
        post_result = self.post(service, task, args, kwargs, workers, uuid, timeout)

        # GET job results
        for result in self.get_iter(
            service, task, [], {}, post_result["workers"], uuid, timeout
        ):
            yield result

        self.running_job = False

    def destroy(self):
        """
        Gracefully shuts down the client.

        This method logs an interrupt message, sets the destroy event, and
        destroys the client context to ensure a clean shutdown.
        """
        log.info(f"{self.name} - client interrupt received, killing client")
        self.destroy_event.set()
        self.ctx.destroy()
