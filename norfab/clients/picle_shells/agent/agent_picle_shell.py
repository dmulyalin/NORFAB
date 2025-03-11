import logging
import json
import yaml

from rich.console import Console
from rich.markdown import Markdown
from picle.models import PipeFunctionsModel, Outputters
from enum import Enum
from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    conlist,
    Field,
)
from typing import Union, Optional, List, Any, Dict, Callable, Tuple
from ..common import ClientRunJobArgs, log_error_or_result, listen_events

RICHCONSOLE = Console()
SERVICE = "agent"
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------------------------
# NETBOX SERVICE SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class AgentShowCommandsModel(BaseModel):
    inventory: Callable = Field(
        "get_inventory",
        description="show agent inventory data",
        json_schema_extra={"outputter": Outputters.outputter_rich_yaml},
    )
    version: Callable = Field(
        "get_version",
        description="show agent service version report",
        json_schema_extra={
            "outputter": Outputters.outputter_rich_yaml,
            "initial_indent": 2,
        },
    )
    status: Callable = Field(
        "get_status",
        description="show agent status",
    )

    class PicleConfig:
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel

    @staticmethod
    def get_inventory(**kwargs):
        workers = kwargs.pop("workers", "all")
        _ = kwargs.pop("progress")
        result = NFCLIENT.run_job("agent", "get_inventory", workers=workers)
        result = log_error_or_result(result)
        return result

    @staticmethod
    def get_version(**kwargs):
        workers = kwargs.pop("workers", "all")
        _ = kwargs.pop("progress")
        result = NFCLIENT.run_job("agent", "get_version", workers=workers)
        result = log_error_or_result(result)
        return result

    @staticmethod
    def get_status(**kwargs):
        workers = kwargs.pop("workers", "any")
        _ = kwargs.pop("progress")
        result = NFCLIENT.run_job("agent", "get_status", workers=workers, kwargs=kwargs)
        result = log_error_or_result(result)
        return result


# ---------------------------------------------------------------------------------------------
# NETBOX SERVICE MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class AgentServiceCommands(ClientRunJobArgs):
    show: AgentShowCommandsModel = Field(
        None, description="Show Agent service parameters"
    )
    chat: StrictStr = Field(
        None,
        description="Chat with the agent",
        json_schema_extra={
            "multiline": True,
            "function": "call_chat",
            "outputter": Outputters.outputter_rich_markdown,
        },
    )
    progress: Optional[StrictBool] = Field(
        True,
        description="Emit execution progress",
        json_schema_extra={"presence": True},
    )

    class PicleConfig:
        subshell = True
        outputter = Outputters.outputter_rich_print
        prompt = "nf[agent]#"

    @staticmethod
    @listen_events
    def call_chat(uuid, *args, **kwargs):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        kwargs["user_input"] = kwargs.pop("chat")
        _ = kwargs.pop("progress")

        # run the job
        result = NFCLIENT.run_job(
            "agent",
            "chat",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            uuid=uuid,
        )
        result = log_error_or_result(result)

        return "\n".join(result.values())
