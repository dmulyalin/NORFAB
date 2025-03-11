import logging

from picle.models import PipeFunctionsModel, Outputters
from enum import Enum
from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    Field,
)
from ..common import ClientRunJobArgs, log_error_or_result, listen_events
from .workflow_picle_shell_run import WorkflowRunShell
from typing import Union, Optional, List, Any, Dict, Callable, Tuple

SERVICE = "workflow"
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# WORKFLOW SERVICE SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class WorkflowShowInventoryModel(ClientRunJobArgs):
    class PicleConfig:
        outputter = Outputters.outputter_rich_yaml
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)

        result = NFCLIENT.run_job(
            "workflow",
            "get_inventory",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
        )
        return log_error_or_result(result)


class WorkflowShowCommandsModel(BaseModel):
    inventory: WorkflowShowInventoryModel = Field(
        None,
        description="show workflow workers inventory data",
    )
    version: Callable = Field(
        "get_version",
        description="show workflow service workers version report",
        json_schema_extra={
            "outputter": Outputters.outputter_rich_yaml,
            "initial_indent": 2,
        },
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def get_version(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("workflow", "get_version", workers=workers)
        return log_error_or_result(result)

    @staticmethod
    def source_workflow():
        workflow_files = NFCLIENT.get(
            "fss.service.broker", "walk", kwargs={"url": "nf://"}
        )
        return workflow_files["results"]

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)

        result = NFCLIENT.run_job(
            "workflow",
            "workflow_run",
            workers=workers,
            args=args,
            kwargs=kwargs,
            uuid=uuid,
            timeout=timeout,
        )

        result = log_error_or_result(result)

        return result


# ---------------------------------------------------------------------------------------------
# WORKFLOW SERVICE MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class WorkflowServiceCommands(BaseModel):
    run: WorkflowRunShell = Field(None, description="Run workflows")
    show: WorkflowShowCommandsModel = Field(
        None, description="Show workflow service workers parameters"
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[workflow]#"
