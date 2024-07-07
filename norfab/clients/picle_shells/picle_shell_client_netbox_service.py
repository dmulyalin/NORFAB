"""
PICLE Shell CLient
==================

Client that implements interactive shell to work with NorFab.
"""
import logging
import json
import yaml

from rich.console import Console
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

NFCLIENT = None  # NFCLIENT updated by parent shell
RICHCONSOLE = Console()
SERVICE = "netbox"
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------------------------


# ---------------------------------------------------------------------------------------------
# COMMON MODELS
# ---------------------------------------------------------------------------------------------


class Targeting(BaseModel):
    instance: Optional[StrictStr] = Field(
        None,
        description="Netbox instance name to target",
    )
    workers: Optional[StrictStr] = Field(
        None,
        description="Netbox workers name to target",
    )

    @staticmethod
    def source_workers():
        reply = NFCLIENT.get(
            "mmi.service.broker",
            "show_workers",
            args=[],
            kwargs={"service": "netbox", "status": "alive"},
        )
        return [i["name"] for i in json.loads(reply)]

    @staticmethod
    def source_instance():
        reply = NFCLIENT.run_job("netbox", "get_netbox_inventory", workers="any")
        for worker_name, inventory in reply.items():
            return list(inventory["instances"])


# ---------------------------------------------------------------------------------------------
# NETBOX SERVICE GRAPHQL SHELL MODEL
# ---------------------------------------------------------------------------------------------


class GrapQLCommands(Targeting):
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Only return query content, do not run it",
        json_schema_extra={"presence": True},
    )
    obj: Optional[StrictStr] = Field(
        None,
        description="Object to return data for e.g. device_list, interface, ip_address",
    )
    filters: Optional[StrictStr] = Field(
        None,
        description="Dictionary of key-value pairs to filter by",
    )
    fields: Optional[StrictStr] = Field(
        None,
        description="List of data fields to return",
    )
    queries: Optional[StrictStr] = Field(
        None,
        description="Dictionary keyed by GraphQL aliases with values of obj, filters, fields dictionary",
    )
    query_string: Optional[StrictStr] = Field(
        None,
        description="Complete GraphQL query string to send as is",
    )

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "any")
        with RICHCONSOLE.status("[bold green]Running query", spinner="dots") as status:
            ret = NFCLIENT.run_job(
                "netbox", "graphql", workers=workers, args=args, kwargs=kwargs
            )
        return ret

    class PicleConfig:
        subshell = True
        prompt = "nf[netbox-graphql]#"
        outputter = Outputters.outputter_rich_json


# ---------------------------------------------------------------------------------------------
# NETBOX SERVICE SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class NetboxShowCommandsModel(Targeting):
    inventory: Callable = Field(
        "get_netbox_inventory",
        description="show Netbox inventory data",
    )
    version: Callable = Field(
        "get_netbox_version",
        description="show Netbox service version report",
    )
    status: Callable = Field(
        "get_netbox_status",
        description="show Netbox status",
    )
    compatibility: Callable = Field(
        "get_compatibility",
        description="show Netbox compatibility",
    )

    class PicleConfig:
        outputter = Outputters.outputter_rich_json
        pipe = PipeFunctionsModel

    @staticmethod
    def get_netbox_inventory(**kwargs):
        workers = kwargs.pop("workers", "all")
        return NFCLIENT.run_job("netbox", "get_netbox_inventory", workers=workers)

    @staticmethod
    def get_netbox_version(**kwargs):
        workers = kwargs.pop("workers", "all")
        return NFCLIENT.run_job("netbox", "get_netbox_version", workers=workers)

    @staticmethod
    def get_netbox_status(**kwargs):
        workers = kwargs.pop("workers", "any")
        return NFCLIENT.run_job(
            "netbox", "get_netbox_status", workers=workers, kwargs=kwargs
        )

    @staticmethod
    def get_compatibility(**kwargs):
        workers = kwargs.pop("workers", "any")
        return NFCLIENT.run_job(
            "netbox", "get_compatibility", workers=workers, kwargs=kwargs
        )


# ---------------------------------------------------------------------------------------------
# NETBOX SERVICE GET SHELL MODEL
# ---------------------------------------------------------------------------------------------


class GetInterfaces(Targeting):
    devices: Union[StrictStr, List] = Field(
        ..., description="Devices to retrieve interface for"
    )
    ip: Optional[StrictBool] = Field(
        None,
        description="Retrieves interface IP addresses",
        json_schema_extra={"presence": True},
    )
    inventory_items: Optional[StrictBool] = Field(
        None,
        description="Retrieves interface inventory items",
        json_schema_extra={"presence": True},
    )
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Only return query content, do not run it",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "any")
        if isinstance(kwargs["devices"], str):
            kwargs["devices"] = [kwargs["devices"]]
        with RICHCONSOLE.status("[bold green]Running query", spinner="dots") as status:
            ret = NFCLIENT.run_job(
                "netbox", "get_interfaces", workers=workers, args=args, kwargs=kwargs
            )
        return ret

    class PicleConfig:
        outputter = Outputters.outputter_rich_json


class GetCommands(BaseModel):
    interfaces: GetInterfaces = Field(
        None, description="Query Netbox device interfaces data"
    )
    # circuits
    # connections
    # devices:

    class PicleConfig:
        subshell = True
        prompt = "nf[netbox-get]#"


# ---------------------------------------------------------------------------------------------
# NETBOX SERVICE MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class NetboxServiceCommands(BaseModel):
    show: NetboxShowCommandsModel = Field(
        None, description="Show Netbox service parameters"
    )
    graphql: GrapQLCommands = Field(None, description="Query Netbox GrapQL API")
    get: GetCommands = Field(None, description="Query data from Netbox")

    # rest
    # get devices
    # get interfaces
    # get connections
    # get circuits

    class PicleConfig:
        subshell = True
        prompt = "nf[netbox]#"
