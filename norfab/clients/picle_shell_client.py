"""
PICLE Shell CLient
==================

Client that implements interactive shell to work with NorFab.
"""
import logging
import json
import yaml

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
from nornir_salt.utils.pydantic_models import model_ffun_fx_filters

GLOBAL = {}
SERVICE = "nornir"
RICHCONSOLE = Console()

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------------------------


def print_rich_table(data: list[dict], headers: list = None, title: str = None):
    headers = headers or list(data[0].keys())
    table = Table(title=title, box=False)

    # add table columns
    for h in headers:
        table.add_column(h, justify="left", no_wrap=True)

    # add table rows
    for item in data:
        cells = [item.get(h, "") for h in headers]
        table.add_row(*cells)

    RICHCONSOLE.print(table)


def print_stats(data: dict):
    for k, v in data.items():
        print(f" {k}: {v}")


def pretty_print_json(data):
    """
    :param data: dictionary or list to print
    """
    try:
        if isinstance(data, bytes):
            data = data.decode("utf-8")

        if not isinstance(data, str):
            data = json.dumps(data)

        # data should be a json string
        RICHCONSOLE.print_json(data, sort_keys=True, indent=4)
    except Exception as e:
        log.error(f"failed to deserialise data into JSON, data '{data}', error {e}")
        RICHCONSOLE.print(data)


def print_nornir_results(data: Union[list, dict]):
    """
    Pretty print Nornir task results.
    
    Order of output is deterministic - same tasks will be printed in same 
    order no matter how many times they are run thanks to sing ``sorted``
    """
    indent = "    "
    for worker in sorted(data.keys()):
        hosts = data[worker]
        if isinstance(hosts, dict):
            for host in sorted(hosts.keys()):
                tasks = hosts[host]
                RICHCONSOLE.print(f"[bold green]{host}[/bold green]:")
                for task in sorted(tasks.keys()):
                    result = tasks[task]
                    RICHCONSOLE.print(f"{1*indent}[bold blue]{task}[/bold blue]:")
                    if isinstance(result, str):
                        for line in result.splitlines():
                            print(f"{2*indent}{line}")
                    elif isinstance(result, dict):
                        for k, v in result.items():
                            lines = str(v).splitlines()
                            if len(lines) == 0:
                                RICHCONSOLE.print(
                                    f"{2*indent}[bold yellow]{k}[/bold yellow]: ''"
                                )
                            elif len(lines) == 1:
                                RICHCONSOLE.print(
                                    f"{2*indent}[bold yellow]{k}[/bold yellow]: {lines[0]}"
                                )
                            else:
                                RICHCONSOLE.print(
                                    f"{2*indent}[bold yellow]{k}[/bold yellow]"
                                )
                                for line in lines:
                                    print(f"{3*indent}{line}")
        elif isinstance(hosts, list):
            print(hosts)


# ---------------------------------------------------------------------------------------------
# SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class filters(BaseModel):
    FO: Optional[Union[Dict, List[Dict]]] = Field(
        None, title="Filter Object", description="Filter hosts using Filter Object"
    )
    FB: Optional[Union[List[str], str]] = Field(
        None,
        title="Filter gloB",
        description="Filter hosts by name using Glob Patterns",
    )
    FH: Optional[Union[List[StrictStr], StrictStr]] = Field(
        None, title="Filter Hostname", description="Filter hosts by hostname"
    )
    FC: Optional[Union[List[str], str]] = Field(
        None,
        title="Filter Contains",
        description="Filter hosts containment of pattern in name",
    )
    FR: Optional[Union[List[str], str]] = Field(
        None,
        title="Filter Regex",
        description="Filter hosts by name using Regular Expressions",
    )
    FG: Optional[StrictStr] = Field(
        None, title="Filter Group", description="Filter hosts by group"
    )
    FP: Optional[Union[List[StrictStr], StrictStr]] = Field(
        None,
        title="Filter Prefix",
        description="Filter hosts by hostname using IP Prefix",
    )
    FL: Optional[Union[List[StrictStr], StrictStr]] = Field(
        None, title="Filter List", description="Filter hosts by names list"
    )
    FM: Optional[Union[List[StrictStr], StrictStr]] = Field(
        None, title="Filter platforM", description="Filter hosts by platform"
    )
    FX: Optional[Union[List[str], str]] = Field(
        None, title="Filter eXclude", description="Filter hosts excluding them by name"
    )
    FN: Optional[StrictBool] = Field(
        None, title="Filter Negate", description="Negate the match"
    )
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Worker to target"
    )
    hosts: Union[StrictStr, List[StrictStr]] = Field(
        None, description="Hosts to target"
    )

    @staticmethod
    def source_workers():
        reply = GLOBAL["client"].get("mmi.service.broker", "show_workers")
        reply = json.loads(reply)
        return [w["name"] for w in reply if w["service"].startswith("nornir")]

    @staticmethod
    def source_hosts():
        ret = set()
        reply = GLOBAL["client"].run_job("nornir", "get_nornir_hosts")
        # reply is a dict keyed by worker name with lists of hosts values
        for worker, hosts in reply.items():
            for host in hosts:
                ret.add(host)
        return list(ret)

    @staticmethod
    def source_FL():
        return filters.source_hosts()

    @staticmethod
    def get_nornir_hosts(**kwargs):
        workers = kwargs.pop("workers", "all")
        reply = GLOBAL["client"].run_job(
            "nornir", "get_nornir_hosts", workers=workers, kwargs=kwargs
        )
        try:
            if isinstance(reply, (bytes, str)):
                return json.dumps(json.loads(reply), indent=4)
            else:
                return reply
        except Exception as e:
            log.error(
                f"failed to deserialise JSON reply, reply content '{reply}', error '{e}'"
            )


class NornirShowCommandsModel(filters):
    inventory: Callable = Field(
        "get_nornir_inventory",
        description="show Nornir inventory data",
    )
    hosts: Callable = Field(
        "print_nornir_hosts",
        description="show Nornir hosts",
    )

    class PicleConfig:
        outputter = Outputters.outputter_rich_json
        
    @staticmethod
    def get_nornir_inventory(**kwargs):
        workers = kwargs.pop("workers", "all")
        reply = GLOBAL["client"].run_job(
            "nornir", "get_nornir_inventory", workers=workers
        )
        return reply

    @staticmethod
    def print_nornir_hosts(**kwargs):
        hosts = filters.get_nornir_hosts(**kwargs)
        return hosts


class WorkerStatus(str, Enum):
    dead = "dead"
    alive = "alive"


class ShowWorkersModel(BaseModel):
    service: StrictStr = Field("all", description="Service name")
    status: WorkerStatus = Field(None, description="Worker status")

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = print_rich_table

    @staticmethod
    def run(*args, **kwargs):
        reply = GLOBAL["client"].get(
            "mmi.service.broker", "show_workers", args=args, kwargs=kwargs
        )
        reply = json.loads(reply)
        return reply


class ShowCommandsModel(BaseModel):
    version: Callable = Field("show_version", description="show current version")
    broker: Callable = Field("show_broker", description="show broker details", outputter=print_stats)
    workers: ShowWorkersModel = Field(None, description="show workers information")
    client: Callable = Field("show_client", description="show client details", outputter=print_stats)
    nornir: NornirShowCommandsModel = Field(None, description="nornir data")

    class PicleConfig:
        pipe = PipeFunctionsModel

    @staticmethod
    def show_version():
        return "NorFab Version 0.1.0"

    @staticmethod
    def show_broker():
        reply = GLOBAL["client"].get("mmi.service.broker", "show_broker")
        return json.loads(reply)

    @staticmethod
    def show_client():
        return {
                "status": "connected",
                "broker": GLOBAL["client"].broker,
                "timeout": GLOBAL["client"].timeout,
                "retries": GLOBAL["client"].retries,
                "recv_queue": GLOBAL["client"].recv_queue.qsize(),
                "base_dir": GLOBAL["client"].base_dir,
                "broker_tx": GLOBAL["client"].stats_send_to_broker,
                "broker_rx": GLOBAL["client"].stats_recv_from_broker,
                "broker_reconnects": GLOBAL["client"].stats_reconnect_to_broker,
            }


# ---------------------------------------------------------------------------------------------
# CLI SHELL NORNIR SERVICE MODELS
# ---------------------------------------------------------------------------------------------


class NrCliPlugins(str, Enum):
    netmiko = "netmiko"
    napalm = "napalm"
    pyats = "pyats"
    scrapli = "scrapli"


class NrCfgPlugins(str, Enum):
    netmiko = "netmiko"
    napalm = "napalm"
    pyats = "pyats"
    scrapli = "scrapli"


class NornirCliShell(filters):
    commands: Optional[Union[StrictStr, List[StrictStr]]] = Field(
        None, description="List of commands to collect form devices"
    )
    plugin: NrCliPlugins = Field("netmiko", description="Connection plugin name")
    add_details: Optional[StrictBool] = Field(
        False, description="Add task details to results", 
        json_schema_extra={"presence": True}
    )
    to_dict: Optional[StrictBool] = Field(
        True, description="Control task results structure"
    )

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "all")
        if kwargs.get("hosts"):
            kwargs["FL"] = kwargs.pop("hosts")
        # first_done = False
        # for reply in GLOBAL["client"].run_job_iter("nornir", "cli", workers=workers, args=args, kwargs=kwargs):
        #     if first_done is False:
        #         print(f"Submitted job to workers {', '.join(reply['workers'])}")
        #         first_done = True
        #     else:
        #         print(f"Received job results")
        #         print_nornir_results(reply)
        with RICHCONSOLE.status(
            "[bold green]Collecting CLI commands", spinner="dots"
        ) as status:
            return GLOBAL["client"].run_job(
                "nornir", "cli", workers=workers, args=args, kwargs=kwargs
            )

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir-cli]#"
        outputter = print_nornir_results


class NornirServiceCommands(BaseModel):
    cli: NornirCliShell = Field(None, description="Send CLI commands to devices")

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir]#"


# ---------------------------------------------------------------------------------------------
# FILE SHELL SERVICE MODELS
# ---------------------------------------------------------------------------------------------


class ListFilesModel(BaseModel):
    url: StrictStr = Field("nf://", description="Directory to list content for")

    class PicleConfig:
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args, **kwargs):
        reply = GLOBAL["client"].get(
            "fss.service.broker", "list_files", args=args, kwargs=kwargs
        )
        pretty_print_json(reply)


class CopyFileModel(BaseModel):
    url: StrictStr = Field("nf://", description="File location")
    destination: Optional[StrictStr] = Field(
        None, description="File location to save downloaded content"
    )
    read: Optional[StrictBool] = Field(False, description="Print file content")

    @staticmethod
    def run(*args, **kwargs):
        status, reply = GLOBAL["client"].fetch_file(**kwargs)
        print(reply)


class ListFileDetails(BaseModel):
    url: StrictStr = Field("nf://", description="File location")

    class PicleConfig:
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args, **kwargs):
        reply = GLOBAL["client"].get(
            "fss.service.broker", "file_details", args=args, kwargs=kwargs
        )
        pretty_print_json(reply)


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
    show: ShowCommandsModel = Field(None, description="show commands")
    nornir: NornirServiceCommands = Field(None, description="Nornir service")
    file: FileServiceCommands = Field(None, description="File sharing service")

    class PicleConfig:
        subshell = True
        prompt = "nf#"
        intro = "Welcome to NorFab Interactive Shell."
        methods_override = {"preloop": "cmd_preloop_override"}

    @classmethod
    def cmd_preloop_override(self):
        """This method called before CMD loop starts"""
        pass
        # log.info("Polling Fabric inventory")
        # GLOBAL["HOSTS"] = filters.get_nornir_hosts()


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
    GLOBAL["client"] = nf.start(
        start_broker=start_broker,
        workers=workers,
        return_client=True,
        # services=services,
    )

    if GLOBAL["client"] is not None:
        # start PICLE interactive shell
        shell = App(NorFabShell)
        shell.start()

        print("Exiting...")
        nf.destroy()
