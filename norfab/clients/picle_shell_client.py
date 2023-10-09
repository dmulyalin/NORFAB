"""
PICLE Shell CLient
==================

Client that implements interactive shell to work with NorFab.
"""
import logging
import json

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
        
# ---------------------------------------------------------------------------------------------
# SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------

class NornirShowCommandsModel(BaseModel):
    inventory: Callable = Field("get_nornir_inventory", description="show Nornir version")
    hosts: Callable = Field("get_nornir_hosts", description="show Nornir hosts")
    
    @staticmethod
    def get_nornir_inventory():
        request = json.dumps(
            {"jid": None, "task": "get_nornir_inventory", "kwargs": {}, "args": []}
        ).encode(encoding="utf-8")
        reply = GLOBAL["client"].send(b"nornir", request)
        return json.dumps(json.loads(reply[0]), indent=4)
            
    @staticmethod
    def get_nornir_hosts():
        request = json.dumps(
            {"jid": None, "task": "get_nornir_hosts", "kwargs": {}, "args": []}
        ).encode(encoding="utf-8")
        reply = GLOBAL["client"].send(b"nornir", request)
        return json.dumps(json.loads(reply[0]), indent=4)
            
            
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
        request = json.dumps(
            {"jid": None, "task": "show_workers", "kwargs": {}, "args": []}
        ).encode(encoding="utf-8")
        reply = GLOBAL["client"].send(b"mmi.broker_utils", request)
        if isinstance(reply, list):
            print_table(json.loads(reply[0]))
        else:
            return reply

    @staticmethod
    def show_broker():
        request = json.dumps(
            {"jid": None, "task": "show_broker", "kwargs": {}, "args": []}
        ).encode(encoding="utf-8")
        reply = GLOBAL["client"].send(b"mmi.broker_utils", request)
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
    netmiko = 'netmiko'
    napalm = 'napalm'
    pyats = 'pyats'
    scrapli = 'scrapli'

class NrCfgPlugins(str, Enum):
    netmiko = 'netmiko'
    napalm = 'napalm'
    pyats = 'pyats'
    scrapli = 'scrapli'
    
class filters(BaseModel):
    FB: StrictStr = Field(None, description="Filter hosts using Glob Pattern")
    FL: List[StrictStr] = Field(None, description="Filter hosts using list of hosts' names")
    hosts: Optional[Union[StrictStr, List[StrictStr]]] = Field(None, description="Select hostnames to run this task for")

    @staticmethod
    def source_hosts():
        return NornirShowCommandsModel.get_nornir_hosts()

class model_nr_cli(filters):
    commands: Optional[Union[StrictStr, List[StrictStr]]] = Field(None, description="List of commands to collect form devices")
    plugin: NrCliPlugins = Field("netmiko", description="Connection plugin name")
        
    @staticmethod
    def run(*args, **kwargs):
        print(f"Called salt nornir cli, args {args}, kwargs: {kwargs}")

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
        """This Methos called before CMD loop starts"""
        log.info("Polling Fabric inventory")
        pass


# ---------------------------------------------------------------------------------------------
# SHELL ENTRY POINT
# ---------------------------------------------------------------------------------------------

def start_picle_shell():
    # initiate NorFab
    nf = NorFab()
    GLOBAL["client"] = nf.start()
    
    # start PICLE interactive shell
    shell = App(NorFabShell)
    shell.start()
    
    print("Exiting...")
    nf.destroy()
