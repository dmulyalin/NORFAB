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
from picle import App
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

GLOBAL = {}
SERVICE = "nornir"
RICHCONSOLE = Console()

logging.basicConfig(
    format="%(asctime)s.%(msecs)d [%(name)s:%(lineno)d %(levelname)s] -- %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------------------------


def print_table(data: list[dict], headers: list = None, title: str = None):
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


def pretty_print_dictionary(data: dict):
    """
    :param data: dictionary keyed by device name
    """
    print(yaml.dump(data, default_flow_style=False))


# ---------------------------------------------------------------------------------------------
# SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class filters(BaseModel):
    FB: StrictStr = Field(None, description="Filter hosts using Glob Pattern")
    FL: List[StrictStr] = Field(
        None, description="Filter hosts using list of hosts' names"
    )
    workers: Union[StrictStr, List[StrictStr]] = Field("any", description="Worker to target")
    
    @staticmethod
    def source_workers():
        request = json.dumps({"task": "show_workers", "kwargs": {}, "args": []})
        reply = GLOBAL["client"].send("mmi.broker_utils", request)
        reply = json.loads(reply[0])
        return [w["name"] for w in reply if w["service"].startswith("nornir")]
        
    @staticmethod
    def get_nornir_hosts(**kwargs):
        ret = []
        workers = kwargs.pop("workers", "any")
        request = json.dumps({"task": "get_nornir_hosts", "kwargs": kwargs, "args": []})
        reply = GLOBAL["client"].send(SERVICE, request, workers)

        for worker_name, hosts in json.loads(reply[0]).items():
            ret.extend(hosts)

        return ret


class NornirShowCommandsModel(filters):
    inventory: Callable = Field(
        "get_nornir_inventory", description="show Nornir inventory data"
    )
    hosts: Callable = Field("print_nornir_hosts", description="show Nornir hosts")

    @staticmethod
    def get_nornir_inventory(**kwargs):
        workers = kwargs.pop("workers", "any")
        request = json.dumps({"task": "get_nornir_inventory", "kwargs": {}, "args": []})
        reply = GLOBAL["client"].send(SERVICE, request, workers)
        try:
            return json.dumps(json.loads(reply[0]), indent=4)
        except:
            log.error(f"failed to deserialise reply into JSON, reply content '{reply}'")

    @staticmethod
    def print_nornir_hosts(**kwargs):
        hosts = filters.get_nornir_hosts(**kwargs)
        return hosts


class ShowCommandsModel(BaseModel):
    version: Callable = Field("show_version", description="show current version")
    broker: Callable = Field("show_broker", description="show broker details")
    workers: Callable = Field("show_workers", description="show workers information")
    client: Callable = Field("show_client", description="show client details")
    nornir: NornirShowCommandsModel = Field(None, description="nornir data")

    @staticmethod
    def show_version():
        return "NorFab Version 0.1.0"

    @staticmethod
    def show_workers():
        request = json.dumps({"task": "show_workers", "kwargs": {}, "args": []})
        reply = GLOBAL["client"].send("mmi.broker_utils", request)
        if isinstance(reply, list):
            print_table(json.loads(reply[0]))
        else:
            return reply

    @staticmethod
    def show_broker():
        request = json.dumps({"task": "show_broker", "kwargs": {}, "args": []})
        reply = GLOBAL["client"].send("mmi.broker_utils", request)
        if isinstance(reply, list):
            print_stats(json.loads(reply[0]))
        else:
            return reply

    @staticmethod
    def show_client():
        print_stats(
            {
                "status": "connected",
                "broker": GLOBAL["client"].broker,
                "timeout": GLOBAL["client"].timeout,
                "retries": GLOBAL["client"].retries,
            }
        )


# ---------------------------------------------------------------------------------------------
# SHELL NORNIR SERVICE MODELS
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


class model_nr_cli(filters):
    commands: Optional[Union[StrictStr, List[StrictStr]]] = Field(
        None, description="List of commands to collect form devices"
    )
    plugin: NrCliPlugins = Field("netmiko", description="Connection plugin name")
    add_details: Optional[StrictBool] = Field(
        False, description="Add task details to results"
    )
    to_dict: Optional[StrictBool] = Field(
        True, description="COntrol task results structure"
    )

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "any")
        request = json.dumps({"task": "cli", "kwargs": kwargs, "args": []})
        reply = GLOBAL["client"].send(SERVICE, request, workers)
        pretty_print_dictionary(json.loads(reply[0]))

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir-cli]#"


class NornirServiceCommands(BaseModel):

    cli: model_nr_cli = Field(None, description="Send CLI commands to devices")

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir]#"


# ---------------------------------------------------------------------------------------------
# MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class NorFabShell(BaseModel):
    show: ShowCommandsModel = Field(None, description="show commands")
    nornir: NornirServiceCommands = Field(None, description="Nornir service")

    class PicleConfig:
        subshell = True
        prompt = "nf#"
        intro = "Welcome to NorFab Interactive Shell."
        methods_override = {"preloop": "cmd_preloop_override"}

    @classmethod
    def cmd_preloop_override(self):
        """This method called before CMD loop starts"""
        log.info("Polling Fabric inventory")
        # GLOBAL["HOSTS"] = filters.get_nornir_hosts()


# ---------------------------------------------------------------------------------------------
# SHELL ENTRY POINT
# ---------------------------------------------------------------------------------------------


def start_picle_shell(
    inventory="./inventory.yaml", workers=None, start_broker=None, services=None
):
    # initiate NorFab
    nf = NorFab(inventory=inventory)
    GLOBAL["client"] = nf.start(
        start_broker=start_broker,
        workers=workers,
        return_client=True,
        services=services,
    )

    if GLOBAL["client"] is not None:
        # start PICLE interactive shell
        shell = App(NorFabShell)
        shell.start()

        print("Exiting...")
        nf.destroy()
