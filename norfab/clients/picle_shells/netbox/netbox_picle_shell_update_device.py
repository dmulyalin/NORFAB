import logging
import json
import yaml

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
from ..nornir.nornir_picle_shell import NornirCommonArgs, NorniHostsFilters
from .netbox_picle_shell_common import NetboxCommonArgs, NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class NornirServiceCommands(NornirCommonArgs):
    @staticmethod
    def run(*args, **kwargs):
        kwargs["via"] = "nornir"
        return UpdateDeviceInterfacesCommand.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class UpdateDatasources(BaseModel):
    nornir: NornirServiceCommands = Field(
        None,
        description="Use Nornir service to retrieve data from devices",
    )


class UpdateDeviceFactsCommand(NetboxCommonArgs, NetboxClientRunJobArgs):
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Return information that would be pushed to Netbox but do not push it",
        json_schema_extra={"presence": True},
        alias="dry-run",
    )
    devices: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="List of Netbox devices to update",
    )
    progress: Optional[StrictBool] = Field(
        True,
        description="Emit execution progress",
        json_schema_extra={"presence": True},
    )
    batch_size: StrictInt = Field(
        10, description="Number of devices to process at a time", alias="batch-size"
    )
    datasource: UpdateDatasources = Field(
        "nornir",
        description="Service to use to retrieve device data",
    )

    @staticmethod
    @listen_events
    def run(uuid, **kwargs):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        kwargs["timeout"] = timeout * 0.9

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]

        result = NFCLIENT.run_job(
            "netbox",
            "update_device_facts",
            workers=workers,
            kwargs=kwargs,
            timeout=timeout,
            uuid=uuid,
        )

        result = log_error_or_result(result)

        return result

    class PicleConfig:
        outputter = Outputters.outputter_nested


class UpdateDeviceInterfacesCommand(NetboxCommonArgs, NetboxClientRunJobArgs):
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Return information that would be pushed to Netbox but do not push it",
        json_schema_extra={"presence": True},
        alias="dry-run",
    )
    devices: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="List of Netbox devices to update",
    )
    progress: Optional[StrictBool] = Field(
        True,
        description="Emit execution progress",
        json_schema_extra={"presence": True},
    )
    datasource: UpdateDatasources = Field(
        "nornir",
        description="Service to use to retrieve device data",
    )
    batch_size: StrictInt = Field(
        10, description="Number of devices to process at a time", alias="batch-size"
    )

    @staticmethod
    @listen_events
    def run(uuid, **kwargs):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        kwargs["timeout"] = timeout * 0.9

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]

        result = NFCLIENT.run_job(
            "netbox",
            "update_device_interfaces",
            workers=workers,
            kwargs=kwargs,
            timeout=timeout,
            uuid=uuid,
        )

        result = log_error_or_result(result)

        return result

    class PicleConfig:
        outputter = Outputters.outputter_nested


class UpdateDeviceIPAddressesCommand(NetboxCommonArgs, NetboxClientRunJobArgs):
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Return information that would be pushed to Netbox but do not push it",
        json_schema_extra={"presence": True},
        alias="dry-run",
    )
    devices: Union[List[StrictStr], StrictStr] = Field(
        None,
        description="List of Netbox devices to update",
    )
    progress: Optional[StrictBool] = Field(
        True,
        description="Emit execution progress",
        json_schema_extra={"presence": True},
    )
    datasource: UpdateDatasources = Field(
        "nornir",
        description="Service to use to retrieve device data",
    )
    batch_size: StrictInt = Field(
        10, description="Number of devices to process at a time", alias="batch-size"
    )

    @staticmethod
    @listen_events
    def run(uuid, **kwargs):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        kwargs["timeout"] = timeout * 0.9

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]

        result = NFCLIENT.run_job(
            "netbox",
            "update_device_ip",
            workers=workers,
            kwargs=kwargs,
            timeout=timeout,
            uuid=uuid,
        )

        result = log_error_or_result(result)

        return result

    class PicleConfig:
        outputter = Outputters.outputter_nested


class UpdateDeviceCommands(BaseModel):
    facts: UpdateDeviceFactsCommand = Field(
        None,
        description="Update device serial, OS version",
    )
    interfaces: UpdateDeviceInterfacesCommand = Field(
        None,
        description="Update device interfaces",
    )
    ip_addresses: UpdateDeviceIPAddressesCommand = Field(
        None, description="Update device interface IP addresses", alias="ip-addresses"
    )
