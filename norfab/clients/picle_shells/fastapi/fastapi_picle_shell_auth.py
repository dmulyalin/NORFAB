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
from uuid import uuid4  # random uuid

log = logging.getLogger(__name__)


class CreateAuthToken(ClientRunJobArgs):
    token: StrictStr = Field(
        None, description="Token string to store, autogenerate if not given"
    )
    username: StrictStr = Field(
        ..., description="Name of the user to store token for", required=True
    )
    expire: StrictInt = Field(None, description="Seconds before token expire")

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)

        if "token" not in kwargs:
            kwargs["token"] = uuid4().hex

        result = NFCLIENT.run_job(
            "fastapi",
            "bearer_token_store",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
        )

        return log_error_or_result(result)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class ListAuthToken(ClientRunJobArgs):
    username: StrictStr = Field(None, description="Name of the user to list tokens for")

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)

        result = NFCLIENT.run_job(
            "fastapi",
            "bearer_token_list",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
        )
        result = log_error_or_result(result)
        ret = []
        for wname, wdata in result.items():
            for token in wdata:
                ret.append({"worker": wname, **token})

        return ret

    class PicleConfig:
        outputter = Outputters.outputter_rich_table
        outputter_kwargs = {"sortby": "worker"}


class DeleteAuthToken(ClientRunJobArgs):
    username: StrictStr = Field(
        None, description="Name of the user to delete tokens for"
    )
    token: StrictStr = Field(None, description="Token string to delete")

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)

        result = NFCLIENT.run_job(
            "fastapi",
            "bearer_token_delete",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
        )

        return log_error_or_result(result)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CheckAuthToken(ClientRunJobArgs):
    token: StrictStr = Field(..., description="Token string to check")

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)

        result = NFCLIENT.run_job(
            "fastapi",
            "bearer_token_check",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
        )

        return log_error_or_result(result)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class FastAPIAuthCommandsModel(BaseModel):
    create_token: CreateAuthToken = Field(
        None, description="Create authentication token", alias="create-token"
    )
    list_tokens: ListAuthToken = Field(
        None, description="Retrieve authentication tokens", alias="list-tokens"
    )
    delete_token: DeleteAuthToken = Field(
        None, description="Delete existing authentication token", alias="delete-token"
    )
    check_token: CheckAuthToken = Field(
        None, description="Check if given token valid", alias="check-token"
    )
