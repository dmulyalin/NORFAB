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
from ..common import ClientRunJobArgs


class NetboxClientRunJobArgs(ClientRunJobArgs):
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "any", description="Filter worker to target"
    )

    @staticmethod
    def source_workers():
        reply = NFCLIENT.get("mmi.service.broker", "show_workers")
        reply = reply["results"]
        return ["all", "any"] + [
            w["name"] for w in reply if w["service"].startswith("netbox")
        ]


class NetboxCommonArgs(BaseModel):
    instance: Optional[StrictStr] = Field(
        None,
        description="Netbox instance name to target",
    )
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "any", description="Filter workers to target"
    )

    @staticmethod
    def source_workers():
        reply = NFCLIENT.get(
            "mmi.service.broker",
            "show_workers",
            args=[],
            kwargs={"service": "netbox", "status": "alive"},
        )
        return [i["name"] for i in reply["results"]]

    @staticmethod
    def source_instance():
        reply = NFCLIENT.run_job("netbox", "get_netbox_inventory", workers="any")
        for worker_name, inventory in reply.items():
            return list(inventory["result"]["instances"])
