import json
import logging
import zmq
import pickle
import os
import sys
import threading
import time

from norfab.core.worker import MajorDomoWorker
from norfab.core.client import MajorDomoClient
from norfab.core.zhelpers import zpipe

from nornir import InitNornir
from uuid import uuid4

SERVICE_DIR = ".__nornir__"

log = logging.getLogger(__name__)


def dumper(data, filename, use_json=False, use_pickle=True):
    if use_json:
        data = data.decode("utf-8")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=4))
    elif use_pickle:
        with open(filename, "wb") as f:
            pickle.dump(data, f)


def loader(filename, use_json=False, use_pickle=True):
    if use_json:
        with open(filename, "r", encoding="utf-8") as f:
            return json.loads(f.read()).encode("utf-8")
    elif use_pickle:
        with open(filename, "rb") as f:
            return pickle.load(f)


def request_filename(suuid):
    """Returns freshly allocated request filename for given UUID str"""
    return os.path.join(SERVICE_DIR, "%s.req" % suuid)


def reply_filename(suuid):
    """Returns freshly allocated reply filename for given UUID str"""
    return os.path.join(SERVICE_DIR, "%s.rep" % suuid)


# ---------------------------------------------------------------------
# Nornir inventory service


def nornir_inventory(broker_endpoint, threads_exit_event):
    worker = MajorDomoWorker(
        broker_endpoint, b"nornir.inventory", "nornir.inventory.worker-1"
    )

    reply = None

    while True:
        # Send reply if it's not null
        # And then get next request from broker
        request = worker.recv(reply)
        if not request:
            break  # Interrupted, exit
        if threads_exit_event.is_set():
            break

        reply = [b"200", {"data": {}}]


# ---------------------------------------------------------------------
# Nornir request service


def nornir_request(broker_endpoint, pipe, threads_exit_event):
    worker = MajorDomoWorker(
        broker_endpoint, b"nornir.request", "nornir.request.worker-1"
    )

    reply = None

    while True:
        # Send reply if it's not null
        # And then get next request from broker
        request = worker.recv(reply)

        log.debug(f"Received request {request}")

        if not request:
            break  # Interrupted, exit
        if threads_exit_event.is_set():
            break

        # Ensure message directory exists
        if not os.path.exists(SERVICE_DIR):
            os.mkdir(SERVICE_DIR)

        # Generate UUID and save message to disk
        suuid = uuid4().hex
        filename = request_filename(suuid)
        dumper(request, filename)

        # Send UUID through to message queue
        pipe.send_string(suuid)

        # Now send UUID back to client
        # Done by the worker.recv() at the top of the loop
        reply = [b"200", suuid.encode("utf-8")]


# ---------------------------------------------------------------------
# Nornir reply service


def nornir_reply(broker_endpoint, threads_exit_event):
    worker = MajorDomoWorker(broker_endpoint, b"nornir.reply", "nornir.reply.worker-1")
    reply = None

    while True:
        request = worker.recv(reply)
        if not request:
            break  # Interrupted, exit
        if threads_exit_event.is_set():
            break

        suuid = request.pop(0).decode("utf-8")
        req_filename = request_filename(suuid)
        rep_filename = reply_filename(suuid)
        if os.path.exists(rep_filename):
            reply = loader(rep_filename)
            reply = [b"200"] + reply
        else:
            if os.path.exists(req_filename):
                reply = [b"300"]  # pending
            else:
                reply = [b"400"]  # unknown


# ---------------------------------------------------------------------
# Nornir close service


def nornir_close(broker_endpoint, threads_exit_event):
    worker = MajorDomoWorker(broker_endpoint, b"nornir.close", "nornir.close.worker-1")
    reply = None

    while True:
        request = worker.recv(reply)
        if not request:
            break  # Interrupted, exit
        if threads_exit_event.is_set():
            break

        suuid = request.pop(0).decode("utf-8")
        req_filename = request_filename(suuid)
        rep_filename = reply_filename(suuid)
        # should these be protected?  Does zfile_delete ignore files
        # that have already been removed?  That's what we are doing here.
        if os.path.exists(req_filename):
            os.remove(req_filename)
        if os.path.exists(rep_filename):
            os.remove(rep_filename)
        reply = [b"200", f"task {suuid} closed".encode("utf-8")]


def service_success(client, suuid):
    """Attempt to process a single request, return True if successful"""
    # Load request message, service will be first frame
    filename = request_filename(suuid)
    service = "nornir"

    # If the client already closed request, treat as successful
    if not os.path.exists(filename):
        return True

    request = loader(filename)

    log.debug(f"processing {suuid} request: {request}")

    # Use MMI protocol to check if service is available
    mmi_request = [json.dumps({"service_name": service})]
    mmi_reply = client.send("mmi.service", mmi_request)

    service_ok = mmi_reply and mmi_reply[0] == b"200"

    if service_ok:
        reply = client.send(service, request)
        if reply:
            filename = reply_filename(suuid)
            dumper(reply, filename)
            return True
    else:
        log.error(
            f"{suuid} request - no service '{service}' registered with broker at {client.broker}"
        )

    return False


class NornirService:
    broker = None
    name = None
    exit_event = None

    def __init__(self, broker, name, exit_event=None):
        self.broker = broker
        self.name = name
        self.exit_event = exit_event
        self.ctx = zmq.Context()

    def start(self):
        # Create MDP client session with short timeout
        client = MajorDomoClient(self.broker)
        client.timeout = 1000  # 1 sec
        client.retries = 1  # only 1 retry

        threads_exit_event = threading.Event()

        request_pipe, peer = zpipe(self.ctx)
        request_thread = threading.Thread(
            target=nornir_request, args=(self.broker, peer, threads_exit_event)
        )
        request_thread.daemon = True
        request_thread.start()
        reply_thread = threading.Thread(
            target=nornir_reply, args=(self.broker, threads_exit_event)
        )
        reply_thread.daemon = True
        reply_thread.start()
        close_thread = threading.Thread(
            target=nornir_close, args=(self.broker, threads_exit_event)
        )
        close_thread.daemon = True
        close_thread.start()
        inventory_thread = threading.Thread(
            target=nornir_inventory, args=(self.broker, threads_exit_event)
        )
        inventory_thread.daemon = True
        inventory_thread.start()

        poller = zmq.Poller()
        poller.register(request_pipe, zmq.POLLIN)

        queue_filename = os.path.join(SERVICE_DIR, "queue")

        log.info(f"{self.name} service started")

        # Main dispatcher loop
        while True:
            # check if need to stop
            if self.exit_event is not None and self.exit_event.is_set():
                threads_exit_event.set()
                self.destroy()
                break

            # Ensure message directory exists
            if not os.path.exists(SERVICE_DIR):
                os.mkdir(SERVICE_DIR)

            # ensure queue file exists
            if not os.path.exists(queue_filename):
                f = open(queue_filename, "wb")
                f.close()

            # We'll dispatch once per second, if there's no activity
            try:
                items = poller.poll(1000)
            except KeyboardInterrupt:
                break
                # Interrupted

            if items:
                # Append UUID to queue, prefixed with '-' for pending
                suuid = request_pipe.recv().decode("utf-8")
                with open(queue_filename, "ab") as f:
                    line = "-%s\n" % suuid
                    f.write(line.encode("utf-8"))

            # Brute-force dispatcher
            with open(queue_filename, "rb+") as f:
                for entry in f.readlines():
                    entry = entry.decode("utf-8")
                    # UUID is prefixed with '-' if still waiting
                    if entry[0] == "-":
                        suuid = entry[1:].rstrip()  # rstrip '\n' etc.
                        log.debug("processing request %s" % suuid)
                        if service_success(client, suuid):
                            # mark queue entry as processed
                            here = f.tell()
                            f.seek(-1 * len(entry), os.SEEK_CUR)
                            f.write("+".encode("utf-8"))
                            f.seek(here, os.SEEK_SET)

    def destroy(self):
        log.info("interrupt received, killing service 'nornir'")
        self.ctx.destroy(0)
