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
from ..common import ClientRunJobArgs, log_error_or_result, listen_events, BoolEnum
from ..nornir.nornir_picle_shell import NornirCommonArgs, NorniHostsFilters
from .netbox_picle_shell_common import NetboxCommonArgs, NetboxClientRunJobArgs

log = logging.getLogger(__name__)


class CacheEnum(Enum):
    TRUE = True
    FALSE = False
    REFRESH = "refresh"
    FORCE = "force"


class CacheList(NetboxClientRunJobArgs, NetboxCommonArgs):
    keys: StrictStr = Field("*", description="Glob pattern to list keys for")
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Filter worker to target"
    )
    details: BoolEnum = Field(
        False, description="Return key details", json_schema_extra={"presence": True}
    )
    table: BoolEnum = Field(
        True,
        description="Print key details in table format",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    def source_workers():
        reply = NFCLIENT.get(
            "mmi.service.broker", "show_workers", kwargs={"service": "netbox"}
        )
        reply = reply["results"]
        return ["all", "any"] + [w["name"] for w in reply]

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers")
        timeout = kwargs.pop("timeout", 600)
        details = kwargs.get("details", False)
        table = kwargs.pop("table", False)

        result = NFCLIENT.run_job(
            "netbox",
            "cache_list",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
        )
        result = log_error_or_result(result)

        if details:
            ret = [
                {
                    "worker": w_name,
                    "key": i["key"],
                    "age": i["age"],
                    "creation": i["creation"],
                    "expires": i["expires"],
                }
                for w_name, w_res in result.items()
                for i in w_res
            ]
            if table:
                return ret, Outputters.outputter_rich_table
            else:
                return ret, Outputters.outputter_rich_json
        else:
            return result

    class PicleConfig:
        pipe = PipeFunctionsModel
        outputter = Outputters.outputter_nested


class CacheClear(NetboxClientRunJobArgs, NetboxCommonArgs):
    key: StrictStr = Field(None, description="Key name to remove from cache")
    keys: StrictStr = Field(
        None, description="Glob pattern of keys to remove from cache"
    )
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Filter worker to target"
    )

    @staticmethod
    def source_workers():
        reply = NFCLIENT.get(
            "mmi.service.broker", "show_workers", kwargs={"service": "netbox"}
        )
        reply = reply["results"]
        return ["all", "any"] + [w["name"] for w in reply]

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers")
        timeout = kwargs.pop("timeout", 600)

        result = NFCLIENT.run_job(
            "netbox",
            "cache_clear",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
        )

        return log_error_or_result(result)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CacheGet(NetboxClientRunJobArgs, NetboxCommonArgs):
    key: StrictStr = Field(None, description="Key name to retrieve data for from cache")
    keys: StrictStr = Field(
        None, description="Glob pattern of keys to retrieve data for from cache"
    )
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Filter worker to target"
    )

    @staticmethod
    def source_workers():
        reply = NFCLIENT.get(
            "mmi.service.broker", "show_workers", kwargs={"service": "netbox"}
        )
        reply = reply["results"]
        return ["all", "any"] + [w["name"] for w in reply]

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers")
        timeout = kwargs.pop("timeout", 600)

        result = NFCLIENT.run_job(
            "netbox",
            "cache_get",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
        )

        return log_error_or_result(result)

    class PicleConfig:
        outputter = Outputters.outputter_rich_json


class NetboxServiceCache(BaseModel):
    list_: CacheList = Field(None, description="List cache keys", alias="list")
    clear: CacheClear = Field(None, description="Clear cache data")
    get: CacheGet = Field(None, description="Get cache data")
