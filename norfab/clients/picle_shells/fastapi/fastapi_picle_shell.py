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
from typing import Union, Optional, List, Any, Dict, Callable, Tuple

SERVICE = "fastapi"
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# FASTAPI SERVICE SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class FastAPIShowInventoryModel(ClientRunJobArgs):
    class PicleConfig:
        outputter = Outputters.outputter_rich_json
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)

        result = NFCLIENT.run_job(
            "fastapi",
            "get_fastapi_inventory",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
        )
        return log_error_or_result(result)


class FastAPIShowCommandsModel(BaseModel):
    inventory: FastAPIShowInventoryModel = Field(
        None,
        description="show FastAPI inventory data",
    )
    version: Callable = Field(
        "get_fastapi_version",
        description="show FastAPI service version report",
    )

    class PicleConfig:
        outputter = Outputters.outputter_rich_json
        pipe = PipeFunctionsModel

    @staticmethod
    def get_fastapi_version(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("fastapi", "get_fastapi_version", workers=workers)
        return log_error_or_result(result)


# ---------------------------------------------------------------------------------------------
# FASTAPI SERVICE MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class FastAPIServiceCommands(BaseModel):
    show: FastAPIShowCommandsModel = Field(
        None, description="Show FastAPI service parameters"
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[fastapi]#"
