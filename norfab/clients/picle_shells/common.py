"""
Common Pydantic Models for PICLE Client Shells
"""
import logging
import time
import threading
import functools
import json
import queue
from uuid import uuid4  # random uuid
from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    Field,
)
from enum import Enum
from typing import Union, Optional, List, Any, Dict, Callable, Tuple
from rich.console import Console

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# COMMON FUNCTIONS
# ---------------------------------------------------------------------------------------------


def listen_events_thread(uuid, stop, NFCLIENT):
    """Helper function to pretty print events to command line"""
    richconsole = Console()
    start_time = time.time()
    time_fmt = "%d-%b-%Y %H:%M:%S"
    richconsole.print(
        f"-" * 45 + " Job Events " + "-" * 47 + "\n"
        f"{time.strftime(time_fmt)} {uuid} job started"
    )
    while not (stop.is_set() or NFCLIENT.exit_event.is_set()):
        try:
            event = NFCLIENT.event_queue.get(block=True, timeout=0.1)
            NFCLIENT.event_queue.task_done()
        except queue.Empty:
            continue
        (
            empty,
            header,
            command,
            service,
            job_uuid,
            status,
            data,
        ) = event
        if job_uuid != uuid.encode("utf-8"):
            NFCLIENT.event_queue.put(event)
            continue

        # extract event parameters
        data = json.loads(data)
        worker = data["worker"]
        service = data["service"]
        task = data["task"]

        # handle per-service event printing
        if service == "nornir":
            timestamp = data["data"]["timestamp"]
            nr_task_name = data["data"]["task_name"]
            nr_task_event = data["data"]["task_event"]
            nr_task_type = data["data"]["task_type"]
            nr_task_hosts = data["data"].get("hosts")
            nr_task_status = data["data"]["status"]
            nr_task_message = data["data"]["message"]
            nr_parent_task = data["data"]["parent_task"]
            nr_task_event = nr_task_event.replace("started", "[cyan]started[/cyan]")
            nr_task_event = nr_task_event.replace(
                "completed", "[green]completed[/green]"
            )
            # log event message
            richconsole.print(
                f"{timestamp} {service} {worker} {', '.join(nr_task_hosts)} {nr_task_type} {nr_task_event} - '{nr_task_name}'"
            )
        elif isinstance(data["data"], (str, int, float)):
            timestamp = data["timestamp"]
            richconsole.print(f"{timestamp} {service} {worker} {task} - {data['data']}")

    elapsed = round(time.time() - start_time, 3)
    richconsole.print(
        f"{time.strftime(time_fmt)} {uuid} job completed in {elapsed} seconds\n\n"
        + f"-" * 45
        + " Job Results "
        + "-" * 44
        + "\n"
    )


def listen_events(fun):
    """Decorator to listen for events and print them to console"""

    @functools.wraps(fun)
    def wrapper(*args, **kwargs):
        events_thread_stop = threading.Event()
        uuid = uuid4().hex
        progress = kwargs.get("progress")

        # start events thread to handle job events printing
        if progress:
            events_thread = threading.Thread(
                target=listen_events_thread,
                name="NornirCliShell_events_listen_thread",
                args=(
                    uuid,
                    events_thread_stop,
                    NFCLIENT,
                ),
            )
            events_thread.start()

        # run decorated function
        try:
            res = fun(uuid, *args, **kwargs)
        finally:
            # stop events thread
            if NFCLIENT and progress:
                events_thread_stop.set()
                events_thread.join()

        return res

    return wrapper


def log_error_or_result(data: dict) -> dict:
    """
    Helper function to log result errors, messages or return results.

    Returns dictionary keyed by worker name with job results as a value.

    :param data: result returned bu NFPCLIENT.run_job function
    """
    ret = {}

    if not isinstance(data, dict):
        log.error(f"Data is not a dictionary but '{type(data)}'")
        return data

    for w_name, w_res in data.items():
        if w_res["errors"]:
            errors = "\n".join(w_res["errors"])
            log.error(f"{w_name} '{w_res['task']}' errors:\n{errors}")
        elif w_res["messages"]:
            messages = "\n".join(w_res["messages"])
            log.info(f"{w_name} '{w_res['task']}' messages:\n{messages}")
        else:
            ret[w_name] = w_res["result"]

    return ret


# ---------------------------------------------------------------------------------------------
# COMMON MODELS
# ---------------------------------------------------------------------------------------------


class BoolEnum(Enum):
    TRUE = True
    FALSE = False


class ClientRunJobArgs(BaseModel):
    timeout: Optional[StrictInt] = Field(None, description="Job timeout")
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Filter worker to target"
    )
