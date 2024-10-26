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
from .common import ClientRunJobArgs, log_error_or_result
from .picle_shell_client_nornir_service import NornirCommonArgs, NorniHostsFilters

NFCLIENT = None  # NFCLIENT updated by parent shell
RICHCONSOLE = Console()
SERVICE = "netbox"
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------------------------
# COMMON MODELS
# ---------------------------------------------------------------------------------------------


class NetboxTargeting(BaseModel):
    instance: Optional[StrictStr] = Field(
        None,
        description="Netbox instance name to target",
    )

    @staticmethod
    def source_workers():
        reply = NFCLIENT.get(
            "mmi.service.broker",
            "show_workers",
            args=[],
            kwargs={"service": "netbox", "status": "alive"},
        )
        return [i["name"] for i in json.loads(reply["results"])]

    @staticmethod
    def source_instance():
        reply = NFCLIENT.run_job("netbox", "get_netbox_inventory", workers="any")
        for worker_name, inventory in reply.items():
            return list(inventory["instances"])


# ---------------------------------------------------------------------------------------------
# NETBOX SERVICE GRAPHQL SHELL MODEL
# ---------------------------------------------------------------------------------------------


class GrapQLCommands(NetboxTargeting, ClientRunJobArgs):
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
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "any", description="Filter worker to target"
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


class NetboxShowCommandsModel(NetboxTargeting, ClientRunJobArgs):
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
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "any", description="Filter worker to target"
    )

    class PicleConfig:
        outputter = Outputters.outputter_rich_json
        pipe = PipeFunctionsModel

    @staticmethod
    def get_netbox_inventory(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("netbox", "get_netbox_inventory", workers=workers)
        result = log_error_or_result(result)
        return result

    @staticmethod
    def get_netbox_version(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("netbox", "get_netbox_version", workers=workers)
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


class GetInterfaces(NetboxTargeting, ClientRunJobArgs):
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
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "any", description="Filter worker to target"
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
# NETBOX SERVICE UPDATE SHELL MODEL
# ---------------------------------------------------------------------------------------------


class UpdateViaNornirServiceCommands(NorniHostsFilters, NornirCommonArgs):
    @staticmethod
    def run(*args, **kwargs):
        kwargs["via"] = "nornir"
        return UpdateDeviceCommands.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_rich_json


class UpdateViaServices(BaseModel):
    nornir: UpdateViaNornirServiceCommands = Field(
        None,
        description="Use Nornir service to retrieve data from devices",
    )


class UpdateDeviceCommands(NetboxTargeting, ClientRunJobArgs):
    via: UpdateViaServices = Field(
        None,
        description="Service to use to retrieve device data",
    )
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Return information that would be pushed to Netbox but do not push it",
        json_schema_extra={"presence": True},
    )
    facts: StrictBool = Field(
        None,
        description="Update device serial, OS version",
        json_schema_extra={"presence": True},
    )
    devices: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="Devices to update",
    )
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "any", description="Filter worker to target"
    )

    @staticmethod
    def run(**kwargs):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        facts = kwargs.pop("facts", False)

        if facts:
            with RICHCONSOLE.status(
                "[bold green]Updating devices facts", spinner="dots"
            ) as status:
                result = NFCLIENT.run_job(
                    "netbox",
                    "update_device_facts",
                    workers=workers,
                    kwargs=kwargs,
                    timeout=timeout,
                )

            result = log_error_or_result(result)

            return result

    class PicleConfig:
        outputter = Outputters.outputter_rich_json


class UpdateComands(BaseModel):
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
    update: UpdateComands = Field(None, description="Update Netbox data")

    # rest
    # get devices
    # get interfaces
    # get connections
    # get circuits

    class PicleConfig:
        subshell = True
        prompt = "nf[netbox]#"
