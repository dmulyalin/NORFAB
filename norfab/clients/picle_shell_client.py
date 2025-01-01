"""
PICLE Shell CLient
==================

Client that implements interactive shell to work with NorFab.
"""
import logging
import json
import yaml
import builtins

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
    root_validator,
    Field,
)
from typing import Union, Optional, List, Any, Dict, Callable, Tuple
from norfab.core.nfapi import NorFab

from .picle_shells.nornir import nornir_picle_shell
from .picle_shells.netbox import netbox_picle_shell

NFCLIENT = None
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------------------------


def print_stats(data: dict):
    for k, v in data.items():
        print(f" {k}: {v}")


# ---------------------------------------------------------------------------------------------
# SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


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
        return json.loads(reply["results"])


class ShowCommandsModel(BaseModel):
    version: Callable = Field("show_version", description="show current version")
    broker: Callable = Field(
        "show_broker", description="show broker details", outputter=print_stats
    )
    workers: ShowWorkersModel = Field(None, description="show workers information")
    client: Callable = Field(
        "show_client", description="show client details", outputter=print_stats
    )
    # jobs: details, summary, last x, failed, pending, completed, by worker

    class PicleConfig:
        pipe = PipeFunctionsModel

    @staticmethod
    def show_version():
        return "NorFab Version 0.1.0"

    @staticmethod
    def show_broker():
        reply = NFCLIENT.get("mmi.service.broker", "show_broker")
        return json.loads(reply["results"])

    @staticmethod
    def show_client():
        return {
            "type": "PICLE Shell",
            "status": "connected",
            "broker": NFCLIENT.broker,
            # "timeout": NFCLIENT.timeout,
            # "retries": NFCLIENT.retries,
            "recv_queue": NFCLIENT.recv_queue.qsize(),
            "base_dir": NFCLIENT.base_dir,
            "broker_tx": NFCLIENT.stats_send_to_broker,
            "broker_rx": NFCLIENT.stats_recv_from_broker,
            "broker_reconnects": NFCLIENT.stats_reconnect_to_broker,
        }


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
        outputter = Outputters.outputter_rich_json


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
        outputter = Outputters.outputter_rich_json


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


def start_picle_shell(
    inventory="./inventory.yaml",
    workers=None,
    start_broker=None,
    log_level="WARNING",
):
    # initiate NorFab
    nf = NorFab(inventory=inventory, log_level=log_level)
    nf.start(start_broker=start_broker, workers=workers)
    NFCLIENT = nf.make_client()

    if NFCLIENT is not None:
        # inject NFCLIENT to all imported models' global space
        builtins.NFCLIENT = NFCLIENT

        try:
            # start PICLE interactive shell
            shell = App(NorFabShell)
            shell.start()

            print("\nExiting...")
            nf.destroy()
        except KeyboardInterrupt:
            print("\nInterrupted by user...")
            nf.destroy()
