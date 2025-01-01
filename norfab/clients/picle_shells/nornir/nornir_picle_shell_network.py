import json

from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    Field,
)
from ..common import ClientRunJobArgs, log_error_or_result, listen_events
from .nornir_picle_shell_common import (
    NorniHostsFilters,
    TabulateTableModel,
    NornirCommonArgs,
    print_nornir_results,
)
from typing import Union, Optional, List, Any, Dict, Callable, Tuple
from nornir_salt.plugins.functions import TabulateFormatter


class NornirNetworkPing(
    NorniHostsFilters, TabulateTableModel, NornirCommonArgs, ClientRunJobArgs
):
    use_host_name: StrictBool = Field(
        None,
        description="Ping host's name instead of host's hostname",
        json_schema_extra={"presence": True},
    )
    count: StrictInt = Field(None, description="Number of pings to run")
    ping_timeout: StrictInt = Field(
        None,
        description="Time in seconds before considering each non-arrived reply permanently lost",
    )
    size: StrictInt = Field(None, description="Size of the entire packet to send")
    interval: Union[int, float] = Field(
        None, description="Interval to wait between pings"
    )
    payload: str = Field(None, description="Payload content if size is not set")
    sweep_start: StrictInt = Field(
        None, description="If size is not set, initial size in a sweep of sizes"
    )
    sweep_end: StrictInt = Field(
        None, description="If size is not set, final size in a sweep of sizes"
    )
    df: StrictBool = Field(
        None,
        description="Don't Fragment flag value for IP Header",
        json_schema_extra={"presence": True},
    )
    match: StrictBool = Field(
        None,
        description="Do payload matching between request and reply",
        json_schema_extra={"presence": True},
    )
    source: StrictStr = Field(None, description="Source IP address")

    class PicleConfig:
        outputter = print_nornir_results

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        kwargs["fun"] = "ping"
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)

        if "ping_timeout" in kwargs:
            kwargs["timeout"] = kwargs.pop("ping_timeout")

        # extract Tabulate arguments
        table = kwargs.pop("table", {})  # tabulate
        headers = kwargs.pop("headers", "keys")  # tabulate
        headers_exclude = kwargs.pop("headers_exclude", [])  # tabulate
        sortby = kwargs.pop("sortby", "host")  # tabulate
        reverse = kwargs.pop("reverse", False)  # tabulate

        if table:
            kwargs["add_details"] = True
            kwargs["to_dict"] = False

        if kwargs.get("hosts"):
            kwargs["FL"] = kwargs.pop("hosts")

        result = NFCLIENT.run_job(
            "nornir",
            "network",
            workers=workers,
            args=args,
            kwargs=kwargs,
            uuid=uuid,
            timeout=timeout,
        )

        result = log_error_or_result(result)

        # form table results
        if table:
            table_data = []
            for w_name, w_res in result.items():
                for item in w_res:
                    item["worker"] = w_name
                    table_data.append(item)
            ret = TabulateFormatter(
                table_data,
                tabulate=table,
                headers=headers,
                headers_exclude=headers_exclude,
                sortby=sortby,
                reverse=reverse,
            )
        else:
            ret = result

        return ret


class NornirNetworkDns(
    NorniHostsFilters, TabulateTableModel, NornirCommonArgs, ClientRunJobArgs
):
    use_host_name: StrictBool = Field(
        None,
        description="Ping host's name instead of host's hostname",
        json_schema_extra={"presence": True},
    )
    servers: Union[StrictStr, List[StrictStr]] = Field(
        None, description="List of DNS servers to use"
    )
    dns_timeout: StrictInt = Field(
        None, description="Time in seconds before considering request lost"
    )
    ipv4: StrictBool = Field(
        None, description="Resolve 'A' record", json_schema_extra={"presence": True}
    )
    ipv6: StrictBool = Field(
        None, description="Resolve 'AAAA' record", json_schema_extra={"presence": True}
    )

    class PicleConfig:
        outputter = print_nornir_results

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        kwargs["fun"] = "resolve_dns"
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)

        if "dns_timeout" in kwargs:
            kwargs["timeout"] = kwargs.pop("dns_timeout")

        # extract Tabulate arguments
        table = kwargs.pop("table", {})  # tabulate
        headers = kwargs.pop("headers", "keys")  # tabulate
        headers_exclude = kwargs.pop("headers_exclude", [])  # tabulate
        sortby = kwargs.pop("sortby", "host")  # tabulate
        reverse = kwargs.pop("reverse", False)  # tabulate

        if table:
            kwargs["add_details"] = True
            kwargs["to_dict"] = False

        if kwargs.get("hosts"):
            kwargs["FL"] = kwargs.pop("hosts")

        result = NFCLIENT.run_job(
            "nornir",
            "network",
            workers=workers,
            args=args,
            kwargs=kwargs,
            uuid=uuid,
            timeout=timeout,
        )

        result = log_error_or_result(result)

        # form table results
        if table:
            table_data = []
            for w_name, w_res in result.items():
                for item in w_res:
                    item["worker"] = w_name
                    table_data.append(item)
            ret = TabulateFormatter(
                table_data,
                tabulate=table,
                headers=headers,
                headers_exclude=headers_exclude,
                sortby=sortby,
                reverse=reverse,
            )
        else:
            ret = result

        return ret


class NornirNetworkShell(BaseModel):
    ping: NornirNetworkPing = Field(None, description="Ping devices")
    dns: NornirNetworkDns = Field(None, description="Resolve DNS")

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir-net]#"
        outputter = print_nornir_results
