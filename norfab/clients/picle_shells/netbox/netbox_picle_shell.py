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
from ..common import log_error_or_result
from .netbox_picle_shell_common import NetboxCommonArgs, NetboxClientRunJobArgs
from .netbox_picle_shell_get_devices import GetDevices
from .netbox_picle_shell_cache import NetboxServiceCache
from .netbox_picle_shell_get_circuits import GetCircuits
from .netbox_picle_shell_update_device import UpdateDeviceCommands

RICHCONSOLE = Console()
SERVICE = "netbox"
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------------------------
# NETBOX SERVICE GRAPHQL SHELL MODEL
# ---------------------------------------------------------------------------------------------


class GrapQLCommands(NetboxClientRunJobArgs, NetboxCommonArgs):
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


class NetboxShowCommandsModel(NetboxClientRunJobArgs, NetboxCommonArgs):
    inventory: Callable = Field(
        "get_inventory",
        description="show Netbox inventory data",
    )
    version: Callable = Field(
        "get_version",
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
    def get_inventory(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("netbox", "get_inventory", workers=workers)
        result = log_error_or_result(result)
        return result

    @staticmethod
    def get_version(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("netbox", "get_version", workers=workers)
        result = log_error_or_result(result)
        return result

    @staticmethod
    def get_netbox_status(**kwargs):
        workers = kwargs.pop("workers", "any")
        result = NFCLIENT.run_job(
            "netbox", "get_netbox_status", workers=workers, kwargs=kwargs
        )
        result = log_error_or_result(result)
        return result

    @staticmethod
    def get_compatibility(**kwargs):
        workers = kwargs.pop("workers", "any")
        result = NFCLIENT.run_job(
            "netbox", "get_compatibility", workers=workers, kwargs=kwargs
        )
        result = log_error_or_result(result)
        return result


# ---------------------------------------------------------------------------------------------
# NETBOX SERVICE GET SHELL MODEL
# ---------------------------------------------------------------------------------------------


class GetInterfaces(NetboxClientRunJobArgs, NetboxCommonArgs):
    devices: Union[StrictStr, List] = Field(
        ..., description="Devices to retrieve interface for"
    )
    ip_addresses: Optional[StrictBool] = Field(
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
        timeout = kwargs.pop("timeout", 600)
        if isinstance(kwargs["devices"], str):
            kwargs["devices"] = [kwargs["devices"]]
        with RICHCONSOLE.status("[bold green]Running query", spinner="dots") as status:
            result = NFCLIENT.run_job(
                "netbox",
                "get_interfaces",
                workers=workers,
                args=args,
                kwargs=kwargs,
                timeout=timeout,
            )
        result = log_error_or_result(result)
        return result

    class PicleConfig:
        outputter = Outputters.outputter_rich_json


class GetCommands(BaseModel):
    devices: GetDevices = Field(None, description="Query Netbox devices data")
    interfaces: GetInterfaces = Field(
        None, description="Query Netbox device interfaces data"
    )
    circuits: GetCircuits = Field(
        None, description="Query Netbox circuits data for devices"
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[netbox-get]#"


# ---------------------------------------------------------------------------------------------
# NETBOX SERVICE UPDATE SHELL MODEL
# ---------------------------------------------------------------------------------------------


class UpdateCommands(BaseModel):
    device: UpdateDeviceCommands = Field(None, description="Update device data")

    class PicleConfig:
        subshell = True
        prompt = "nf[netbox-update]#"


# ---------------------------------------------------------------------------------------------
# NETBOX SERVICE MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class NetboxServiceCommands(BaseModel):
    show: NetboxShowCommandsModel = Field(
        None, description="Show Netbox service parameters"
    )
    graphql: GrapQLCommands = Field(None, description="Query Netbox GrapQL API")
    get: GetCommands = Field(None, description="Query data from Netbox")
    update: UpdateCommands = Field(None, description="Update Netbox data")
    cache: NetboxServiceCache = Field(
        None, description="Work with Netbox service cached data"
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[netbox]#"
