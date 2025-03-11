"""
PICLE Shell CLient
==================

Client that implements interactive shell to work with NorFab.
"""
import logging
import json
import yaml
import builtins
import importlib.metadata
import sys

from rich.console import Console
from rich.table import Table
from rich.pretty import pprint as rich_pprint
from picle import App
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
from norfab.core.nfapi import NorFab

from .picle_shells.nornir import nornir_picle_shell
from .picle_shells.netbox import netbox_picle_shell
from .picle_shells.agent import agent_picle_shell
from .picle_shells.fastapi import fastapi_picle_shell
from .picle_shells.norfab_jobs_shell import NorFabJobsShellCommands
from .picle_shells.workflow import workflow_picle_shell

NFCLIENT = None
RICHCONSOLE = Console()
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------------------------


# ---------------------------------------------------------------------------------------------
# SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class ShowBrokerModel(BaseModel):
    version: StrictBool = Field(
        False,
        description="Show broker version report",
        json_schema_extra={"presence": True},
    )
    inventory: StrictBool = Field(
        False, description="Show broker inventory", json_schema_extra={"presence": True}
    )

    class PicleConfig:
        outputter = Outputters.outputter_rich_yaml
        outputter_kwargs = {"initial_indent": 2}

    @staticmethod
    def run(*args, **kwargs):
        if kwargs.get("version"):
            reply = NFCLIENT.get("mmi.service.broker", "show_broker_version")
        elif kwargs.get("inventory"):
            reply = NFCLIENT.get("mmi.service.broker", "show_broker_inventory")
        else:
            reply = NFCLIENT.get("mmi.service.broker", "show_broker")
        if reply["errors"]:
            return "\n".join(reply["errors"])
        else:
            return reply["results"]


class WorkerStatus(str, Enum):
    dead = "dead"
    alive = "alive"
    any_ = "any"


class ShowWorkersModel(BaseModel):
    service: StrictStr = Field("all", description="Service name")
    status: WorkerStatus = Field("any", description="Worker status")

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_rich_table
        outputter_kwargs = {"sortby": "name"}

    @staticmethod
    def run(*args, **kwargs):
        reply = NFCLIENT.get(
            "mmi.service.broker", "show_workers", args=args, kwargs=kwargs
        )
        if reply["errors"]:
            return "\n".join(reply["errors"])
        else:
            return reply["results"]


class ShowCommandsModel(BaseModel):
    version: Callable = Field(
        "show_version",
        description="show nfcli client version report",
    )
    jobs: NorFabJobsShellCommands = Field(
        None, description="Show NorFab Jobs for all services"
    )
    broker: ShowBrokerModel = Field(None, description="show broker details")
    workers: ShowWorkersModel = Field(None, description="show workers information")
    client: Callable = Field("show_client", description="Show client details")
    inventory: Callable = Field(
        "show_inventory",
        description="Show NorFab inventory",
        json_schema_extra={"outputter": Outputters.outputter_rich_yaml},
    )

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_rich_yaml
        outputter_kwargs = {"initial_indent": 2}

    @staticmethod
    def show_version():
        libs = {
            "norfab": "",
            "pyyaml": "",
            "pyzmq": "",
            "psutil": "",
            "tornado": "",
            "jinja2": "",
            "picle": "",
            "rich": "",
            "tabulate": "",
            "pydantic": "",
            "pyreadline3": "",
            "python": sys.version.split(" ")[0],
            "platform": sys.platform,
        }
        # get version of packages installed
        for pkg in libs.keys():
            try:
                libs[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                pass

        return libs

    @staticmethod
    def show_client():
        return {
            "client-type": "PICLE Shell",
            "status": "connected",
            "name": NFCLIENT.name,
            "zmq-name": NFCLIENT.zmq_name,
            "recv-queue-size": NFCLIENT.recv_queue.qsize(),
            "broker": {
                "endpoint": NFCLIENT.broker,
                "reconnects": NFCLIENT.stats_reconnect_to_broker,
                "messages-rx": NFCLIENT.stats_recv_from_broker,
                "messages-tx": NFCLIENT.stats_send_to_broker,
            },
            "directories": {
                "base-dir": NFCLIENT.base_dir,
                "jobs-dir": NFCLIENT.jobs_dir,
                "events-dir": NFCLIENT.events_dir,
                "public-keys-dir": NFCLIENT.public_keys_dir,
                "private-keys-dir": NFCLIENT.private_keys_dir,
            },
            "security": {
                "client-private-key-file": NFCLIENT.client_private_key_file,
                "broker-public-key-file": NFCLIENT.broker_public_key_file,
            },
        }

    @staticmethod
    def show_inventory():
        return NFCLIENT.inventory.dict()


# ---------------------------------------------------------------------------------------------
# FILE SHELL SERVICE MODELS
# ---------------------------------------------------------------------------------------------


class ListFilesModel(BaseModel):
    url: StrictStr = Field("nf://", description="Directory to list content for")

    @staticmethod
    def run(*args, **kwargs):
        reply = NFCLIENT.get(
            "fss.service.broker", "list_files", args=args, kwargs=kwargs
        )
        return reply

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested


class CopyFileModel(BaseModel):
    url: StrictStr = Field("nf://", description="File location")
    destination: Optional[StrictStr] = Field(
        None, description="File location to save downloaded content"
    )
    read: Optional[StrictBool] = Field(False, description="Print file content")

    @staticmethod
    def run(*args, **kwargs):
        status, reply = NFCLIENT.fetch_file(**kwargs)
        return reply

    class PicleConfig:
        outputter = Outputters.outputter_rich_print


class ListFileDetails(BaseModel):
    url: StrictStr = Field("nf://", description="File location")

    @staticmethod
    def run(*args, **kwargs):
        reply = NFCLIENT.get(
            "fss.service.broker", "file_details", args=args, kwargs=kwargs
        )
        return reply

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested


class FileServiceCommands(BaseModel):
    """
    # Sample Usage

    ## copy

    Copy to client's fetched files directory:

    ``file copy_ url nf://cli/commands.txt``

    Copy file to destination relative to current directory

    ``file copy_ url nf://cli/commands.txt destination commands.txt``

    ## list

    List files at broker root directory:

    ``
    file list
    file list url nf://
    ``

    List files details:

    ```
    file details
    file details url nf://
    ```
    """

    list_: ListFilesModel = Field(None, description="List files", alias="list")
    copy_: CopyFileModel = Field(None, description="Copy files", alias="copy")
    details: ListFileDetails = Field(None, description="Show file details")


# ---------------------------------------------------------------------------------------------
# MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class NorFabShell(BaseModel):
    show: ShowCommandsModel = Field(None, description="NorFab show commands")
    file: FileServiceCommands = Field(None, description="File sharing service")
    nornir: nornir_picle_shell.NornirServiceCommands = Field(
        None, description="Nornir service"
    )
    netbox: netbox_picle_shell.NetboxServiceCommands = Field(
        None, description="Netbox service"
    )
    agent: agent_picle_shell.AgentServiceCommands = Field(
        None, description="AI Agent service"
    )
    fastapi: fastapi_picle_shell.FastAPIServiceCommands = Field(
        None, description="FastAPI service"
    )
    workflow: workflow_picle_shell.WorkflowServiceCommands = Field(
        None, description="Workflow service"
    )

    class PicleConfig:
        subshell = True
        prompt = "nf#"
        intro = "Welcome to NorFab Interactive Shell."
        methods_override = {"preloop": "cmd_preloop_override"}

    @classmethod
    def cmd_preloop_override(self):
        """This method called before CMD loop starts"""
        pass


# ---------------------------------------------------------------------------------------------
# SHELL ENTRY POINT
# ---------------------------------------------------------------------------------------------


def mount_shell_plugins(shell: App, inventory: object) -> None:
    """
    Mounts shell plugins to the given shell application.

    This function iterates over the plugins in the inventory and mounts
    those that have an "nfcli" configuration to the shell application.

    Args:
        shell (App): The shell application to which the plugins will be mounted.
        inventory (object): An object containing the plugins to be mounted.
                            It should have an attribute `plugins` which is a dictionary
                            where keys are service names and values are service data dictionaries.

    Returns:
        None
    """
    for service_name, service_data in inventory.plugins.items():
        if service_data.get("nfcli"):
            shell.model_mount(
                path=service_data["nfcli"]["mount_path"],
                model=service_data["nfcli"]["shell_model"],
            )


def start_picle_shell(
    inventory="./inventory.yaml",
    workers=None,
    start_broker=None,
    log_level="WARNING",
):
    global NFCLIENT
    # initiate NorFab
    nf = NorFab(inventory=inventory, log_level=log_level)
    nf.start(start_broker=start_broker, workers=workers)
    NFCLIENT = nf.make_client()

    if NFCLIENT is not None:
        # inject NFCLIENT to all imported models' global space
        builtins.NFCLIENT = NFCLIENT

        # start PICLE interactive shell
        shell = App(NorFabShell)
        mount_shell_plugins(shell, nf.inventory)
        shell.start()

        print("Exiting...")
        nf.destroy()
