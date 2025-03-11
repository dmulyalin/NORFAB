import json
import pprint

from typing import Union, Optional, List, Any, Dict, Callable, Tuple
from enum import Enum
from pydantic import (
    StrictStr,
    Field,
    BaseModel,
    StrictInt,
    StrictBool,
)
from ..common import ClientRunJobArgs, log_error_or_result
from nornir_salt.plugins.functions import TabulateFormatter
from picle.models import Outputters


class NornirTaskEnum(str, Enum):
    cli = "cli"
    parse = "parse"
    cfg = "cfg"
    task = "task"
    test = "test"
    network = "network"
    diagram = "diagram"


class ListJobsModel(ClientRunJobArgs):
    workers: StrictStr = Field("all", description="Workers to return jobs for")
    last: StrictInt = Field(
        None, description="Return last N completed and last N pending jobs"
    )
    pending: StrictBool = Field(
        True, description="Return pending jobs", json_schema_extra={"presence": True}
    )
    completed: StrictBool = Field(
        True, description="Return completed jobs", json_schema_extra={"presence": True}
    )
    client: StrictStr = Field(None, description="Client name to return jobs for")
    uuid: StrictStr = Field(None, description="Job UUID to return")
    task: NornirTaskEnum = Field(None, description="Task name to return jobs for")

    @staticmethod
    def source_client():
        return ["self"]

    @staticmethod
    def source_workers():
        reply = NFCLIENT.get(
            "mmi.service.broker", "show_workers", kwargs={"service": "nornir"}
        )
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)

        if kwargs.get("client") == "self":
            kwargs["client"] = NFCLIENT.zmq_name

        result = NFCLIENT.run_job(
            "nornir",
            "job_list",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
        )
        result = log_error_or_result(result)

        ret = []
        for worker_name, worker_results in result.items():
            ret.extend(worker_results)

        return ret

    class PicleConfig:
        outputter = Outputters.outputter_rich_table


class JobDetailsModel(ClientRunJobArgs):
    uuid: StrictStr = Field(..., description="Job UUID", mandatory=True)
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Workers to return jobs for"
    )
    data: StrictBool = Field(
        True,
        description="Return job data received from client",
        json_schema_extra={"presence": True},
    )
    result: StrictBool = Field(
        True, description="Return job result", json_schema_extra={"presence": True}
    )
    events: StrictBool = Field(
        True, description="Return job events", json_schema_extra={"presence": True}
    )

    @staticmethod
    def source_workers():
        reply = NFCLIENT.get(
            "mmi.service.broker", "show_workers", kwargs={"service": "nornir"}
        )
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)

        result = NFCLIENT.run_job(
            "nornir",
            "job_details",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
        )
        result = log_error_or_result(result)

        return result

    class PicleConfig:
        outputter = Outputters.outputter_nested


class NornirJobsShell(BaseModel):
    summary: ListJobsModel = Field(None, description="List jobs")
    details: JobDetailsModel = Field(None, description="Show job details")

    class PicleConfig:
        pass
