import json

from typing import Union, Optional, List, Any, Dict, Callable, Tuple
from pydantic import (
    StrictStr,
    Field,
    BaseModel,
    StrictInt,
    StrictBool,
)
from .common import ClientRunJobArgs, log_error_or_result
from nornir_salt.plugins.functions import TabulateFormatter
from picle.models import Outputters


class ListJobsModel(ClientRunJobArgs):
    service: StrictStr = Field(
        ..., description="Service name to return jobs for", mandatory=True
    )
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
    task: StrictStr = Field(None, description="Task name to return jobs for")
    client: StrictStr = Field(None, description="Client name to return jobs for")
    uuid: StrictStr = Field(None, description="Job UUID to return")

    @staticmethod
    def source_service():
        return ["netbox", "nornir"]

    @staticmethod
    def source_workers():
        reply = NFCLIENT.get("mmi.service.broker", "show_workers")
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)

        result = NFCLIENT.run_job(
            kwargs.pop("service"),
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
    service: StrictStr = Field(
        ..., description="Service name to return job details for", mandatory=True
    )
    workers: StrictStr = Field("all", description="Workers to return jobs for")
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
    def source_service():
        return ["netbox", "nornir"]

    @staticmethod
    def source_workers():
        reply = NFCLIENT.get("mmi.service.broker", "show_workers")
        workers = [i["name"] for i in reply["results"]]

        return ["all", "any"] + workers

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)

        result = NFCLIENT.run_job(
            kwargs.pop("service"),
            "job_details",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
        )
        result = log_error_or_result(result)

        return result

    class PicleConfig:
        outputter = Outputters.outputter_rich_print


class NorFabJobsShellCommands(BaseModel):
    summary: ListJobsModel = Field(None, description="List jobs")
    details: JobDetailsModel = Field(None, description="Show job details")

    class PicleConfig:
        subshell = True
        prompt = "nf[jobs]#"
