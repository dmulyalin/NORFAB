import json

from enum import Enum
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


class NapalmGettersEnum(str, Enum):
    get_arp_table = "get_arp_table"
    get_bgp_config = "get_bgp_config"
    get_bgp_neighbors = "get_bgp_neighbors"
    get_bgp_neighbors_detail = "get_bgp_neighbors_detail"
    get_config = "get_config"
    get_environment = "get_environment"
    get_facts = "get_facts"
    get_firewall_policies = "get_firewall_policies"
    get_interfaces = "get_interfaces"
    get_interfaces_counters = "get_interfaces_counters"
    get_interfaces_ip = "get_interfaces_ip"
    get_ipv6_neighbors_table = "get_ipv6_neighbors_table"
    get_lldp_neighbors = "get_lldp_neighbors"
    get_lldp_neighbors_detail = "get_lldp_neighbors_detail"
    get_mac_address_table = "get_mac_address_table"
    get_network_instances = "get_network_instances"
    get_ntp_peers = "get_ntp_peers"
    get_ntp_servers = "get_ntp_servers"
    get_ntp_stats = "get_ntp_stats"
    get_optics = "get_optics"
    get_probes_config = "get_probes_config"
    get_probes_results = "get_probes_results"
    get_route_to = "get_route_to"
    get_snmp_information = "get_snmp_information"
    get_users = "get_users"
    get_vlans = "get_vlans"
    is_alive = "is_alive"
    ping = "ping"
    traceroute = "traceroute"


class NapalmGettersModel(NorniHostsFilters, NornirCommonArgs, ClientRunJobArgs):
    getters: NapalmGettersEnum = Field(
        ..., description="Select NAPALM getters", required=True
    )

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)

        if kwargs.get("hosts"):
            kwargs["FL"] = kwargs.pop("hosts")

        result = NFCLIENT.run_job(
            "nornir",
            "parse",
            workers=workers,
            args=args,
            kwargs={"plugin": "napalm", **kwargs},
            uuid=uuid,
            timeout=timeout,
        )

        return log_error_or_result(result)

    class PicleConfig:
        outputter = print_nornir_results


class TTPParseModel(NorniHostsFilters, NornirCommonArgs, ClientRunJobArgs):
    template: StrictStr = Field(
        ..., description="TTP Template to parse commands output", required=True
    )
    commands: Union[List[StrictStr], StrictStr] = Field(
        None, description="Commands to collect form devices"
    )

    @staticmethod
    def source_template():
        broker_files = NFCLIENT.get(
            "fss.service.broker", "walk", kwargs={"url": "nf://"}
        )
        return json.loads(broker_files["results"])

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)

        if kwargs.get("hosts"):
            kwargs["FL"] = kwargs.pop("hosts")

        result = NFCLIENT.run_job(
            "nornir",
            "parse",
            workers=workers,
            args=args,
            kwargs={"plugin": "ttp", **kwargs},
            uuid=uuid,
            timeout=timeout,
        )

        return log_error_or_result(result)

    class PicleConfig:
        outputter = print_nornir_results


class NornirParseShell(BaseModel):
    napalm: NapalmGettersModel = Field(
        None, description="Parse devices output using NAPALM getters"
    )
    ttp: TTPParseModel = Field(
        None, description="Parse devices output using TTP templates"
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir-parse]#"
        outputter = print_nornir_results
