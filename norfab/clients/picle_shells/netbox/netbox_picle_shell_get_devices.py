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
from .netbox_picle_shell_cache import CacheEnum

log = logging.getLogger(__name__)


class GetDevices(NetboxClientRunJobArgs, NetboxCommonArgs):
    filters: StrictStr = Field(
        None,
        description="List of device filters dictionaries as a JSON string",
        examples='[{"q": "ceos1"}]',
    )
    devices: Union[StrictStr, List[StrictStr]] = Field(
        None, description="Device names to query data for", alias="device-list"
    )
    dry_run: StrictBool = Field(
        None,
        description="Only return query content, do not run it",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    cache: CacheEnum = Field(True, description="How to use cache")

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)

        if isinstance(kwargs.get("devices"), str):
            kwargs["devices"] = [kwargs["devices"]]
        if isinstance(kwargs.get("filters"), str):
            kwargs["filters"] = json.loads(kwargs["filters"])

        result = NFCLIENT.run_job(
            "netbox",
            "get_devices",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
        )

        return log_error_or_result(result)

    class PicleConfig:
        outputter = Outputters.outputter_rich_json
