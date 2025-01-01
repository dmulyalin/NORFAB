import logging
import json
import time
import os
import copy

from fnmatch import fnmatchcase
from picle.models import PipeFunctionsModel, Outputters
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
from nornir_salt.plugins.functions import TabulateFormatter

try:
    import N2G

    HAS_N2G = True
except ImportError:
    HAS_N2G = False

try:
    from ttp import ttp
    from ttp_templates import list_templates as list_ttp_templates

    HAS_TTP = True
except ImportError:
    HAS_TTP = False

log = logging.getLogger(__name__)


class N2GDiagramAppEnum(str, Enum):
    yed = "yed"
    drawio = "drawio"
    v3d = "v3d"


class N2GLayer3Diagram(NorniHostsFilters, NornirCommonArgs):
    group_links: StrictBool = Field(
        None,
        description="Group links between same nodes",
        json_schema_extra={"presence": True},
    )
    add_arp: StrictBool = Field(
        None,
        description="Add IP nodes from ARP cache parsing results",
        json_schema_extra={"presence": True},
    )
    label_interface: StrictBool = Field(
        None,
        description="Add interface name to the link’s source and target labels",
        json_schema_extra={"presence": True},
    )
    label_vrf: StrictBool = Field(
        None,
        description="Add VRF name to the link’s source and target labels",
        json_schema_extra={"presence": True},
    )
    collapse_ptp: StrictBool = Field(
        None,
        description="Combines links for /31 and /30 IPv4 and /127 IPv6 subnets into a single link",
        json_schema_extra={"presence": True},
    )
    add_fhrp: StrictBool = Field(
        None,
        description="Add HSRP and VRRP IP addresses to the diagram",
        json_schema_extra={"presence": True},
    )
    bottom_label_length: StrictInt = Field(
        None,
        description="Length of interface description to use for subnet labels, if 0, label not set",
    )
    lbl_next_to_subnet: StrictBool = Field(
        None,
        description="Put link port:vrf:ip label next to subnet node",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    def run(*args, **kwargs):
        kwargs["data_plugin"] = "layer3"
        n2g_kwargs = {}
        kwargs["n2g_kwargs"] = n2g_kwargs
        if "group_links" in kwargs:
            n2g_kwargs["group_links"] = kwargs.pop("group_links")
        if "add_arp" in kwargs:
            n2g_kwargs["add_arp"] = kwargs.pop("add_arp")
        if "label_interface" in kwargs:
            n2g_kwargs["label_interface"] = kwargs.pop("label_interface")
        if "label_vrf" in kwargs:
            n2g_kwargs["label_vrf"] = kwargs.pop("label_vrf")
        if "collapse_ptp" in kwargs:
            n2g_kwargs["collapse_ptp"] = kwargs.pop("collapse_ptp")
        if "add_fhrp" in kwargs:
            n2g_kwargs["add_fhrp"] = kwargs.pop("add_fhrp")
        if "bottom_label_length" in kwargs:
            n2g_kwargs["bottom_label_length"] = kwargs.pop("bottom_label_length")
        if "lbl_next_to_subnet" in kwargs:
            n2g_kwargs["lbl_next_to_subnet"] = kwargs.pop("lbl_next_to_subnet")

        return NornirDiagramShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_rich_print


class N2GLayer2Diagram(NorniHostsFilters, NornirCommonArgs):
    add_interfaces_data: StrictBool = Field(
        None,
        description="Add interfaces configuration and state data to links",
        json_schema_extra={"presence": True},
    )
    group_links: StrictBool = Field(
        None,
        description="Group links between nodes",
        json_schema_extra={"presence": True},
    )
    add_lag: StrictBool = Field(
        None,
        description="Add LAG/MLAG links to diagram",
        json_schema_extra={"presence": True},
    )
    add_all_connected: StrictBool = Field(
        None,
        description="Add all nodes connected to devices based on interfaces state",
        json_schema_extra={"presence": True},
    )
    combine_peers: StrictBool = Field(
        None,
        description="Combine CDP/LLDP peers behind same interface by adding L2 node",
        json_schema_extra={"presence": True},
    )
    skip_lag: StrictBool = Field(
        None,
        description="Skip CDP peers for LAG, some platforms send CDP/LLDP PDU from LAG ports",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    def run(*args, **kwargs):
        kwargs["data_plugin"] = "layer2"
        n2g_kwargs = {}
        kwargs["n2g_kwargs"] = n2g_kwargs
        if "add_interfaces_data" in kwargs:
            n2g_kwargs["add_interfaces_data"] = kwargs.pop("add_interfaces_data")
        if "group_links" in kwargs:
            n2g_kwargs["group_links"] = kwargs.pop("group_links")
        if "add_lag" in kwargs:
            n2g_kwargs["add_lag"] = kwargs.pop("add_lag")
        if "add_all_connected" in kwargs:
            n2g_kwargs["add_all_connected"] = kwargs.pop("add_all_connected")
        if "combine_peers" in kwargs:
            n2g_kwargs["combine_peers"] = kwargs.pop("combine_peers")
        if "skip_lag" in kwargs:
            n2g_kwargs["skip_lag"] = kwargs.pop("skip_lag")

        return NornirDiagramShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_rich_print


class N2GISISDiagram(NorniHostsFilters, NornirCommonArgs):
    ip_lookup_data: StrictStr = Field(
        None,
        description="IP Lookup dictionary or OS path to CSV file",
    )
    add_connected: StrictBool = Field(
        None,
        description="Add connected subnets as nodes",
        json_schema_extra={"presence": True},
    )
    ptp_filter: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="List of glob patterns to filter point-to-point links based on link IP",
    )
    add_data: StrictBool = Field(
        None,
        description="Add data information to nodes and links",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    def run(*args, **kwargs):
        kwargs["data_plugin"] = "isis"
        n2g_kwargs = {}
        kwargs["n2g_kwargs"] = n2g_kwargs
        if "ip_lookup_data" in kwargs:
            n2g_kwargs["ip_lookup_data"] = kwargs.pop("ip_lookup_data")
        if "add_connected" in kwargs:
            n2g_kwargs["add_connected"] = kwargs.pop("add_connected")
        if "ptp_filter" in kwargs:
            n2g_kwargs["ptp_filter"] = kwargs.pop("ptp_filter")
        if "add_data" in kwargs:
            n2g_kwargs["add_data"] = kwargs.pop("add_data")

        return NornirDiagramShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_rich_print


class N2GOSPFDiagram(NorniHostsFilters, NornirCommonArgs):
    ip_lookup_data: StrictStr = Field(
        None,
        description="IP Lookup dictionary or OS path to CSV file",
    )
    add_connected: StrictBool = Field(
        None,
        description="Add connected subnets as nodes",
        json_schema_extra={"presence": True},
    )
    ptp_filter: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="List of glob patterns to filter point-to-point links based on link IP",
    )
    add_data: StrictBool = Field(
        None,
        description="Add data information to nodes and links",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    def run(*args, **kwargs):
        kwargs["data_plugin"] = "ospf"
        n2g_kwargs = {}
        kwargs["n2g_kwargs"] = n2g_kwargs
        if "ip_lookup_data" in kwargs:
            n2g_kwargs["ip_lookup_data"] = kwargs.pop("ip_lookup_data")
        if "add_connected" in kwargs:
            n2g_kwargs["add_connected"] = kwargs.pop("add_connected")
        if "ptp_filter" in kwargs:
            n2g_kwargs["ptp_filter"] = kwargs.pop("ptp_filter")
        if "add_data" in kwargs:
            n2g_kwargs["add_data"] = kwargs.pop("add_data")

        return NornirDiagramShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_rich_print


class NornirDiagramShell(ClientRunJobArgs, NorniHostsFilters):
    format: N2GDiagramAppEnum = Field("yed", description="Diagram application format")
    layer3: N2GLayer3Diagram = Field(
        None, description="Create L3 Network diagram using IP data"
    )
    layer2: N2GLayer2Diagram = Field(
        None, description="Create L2 Network diagram using CDP/LLDP data"
    )
    isis: N2GISISDiagram = Field(
        None, description="Create ISIS Network diagram using LSDB data"
    )
    ospf: N2GOSPFDiagram = Field(
        None, description="Create OSPF Network diagram using LSDB data"
    )
    filename: StrictStr = Field(
        None, description="Name of the file to save diagram content"
    )

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        if not (HAS_N2G and HAS_TTP):
            return f"Failed importing N2G and TTP modules, are they installed?"

        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        ctime = time.strftime("%Y-%m-%d_%H-%M-%S")
        FM = kwargs.pop("FM", [])
        n2g_data = {}  # to store collected from devices data
        diagram_plugin = kwargs.pop("format")
        data_plugin = kwargs.pop("data_plugin")
        n2g_kwargs = kwargs.pop("n2g_kwargs")
        hosts_processed = set()

        if kwargs.get("hosts"):
            kwargs["FL"] = kwargs.pop("hosts")

        drawing_plugin, ext = {
            "yed": (N2G.yed_diagram, "graphml"),
            "drawio": (N2G.drawio_diagram, "drawio"),
            "v3d": (N2G.v3d_diagramm, "json"),
        }[diagram_plugin]

        template_dir, n2g_data_plugin = {
            "layer2": ("cli_l2_data", N2G.cli_l2_data),
            "layer3": ("cli_ip_data", N2G.cli_ip_data),
            "isis": ("cli_isis_data", N2G.cli_isis_data),
            "ospf": ("cli_ospf_data", N2G.cli_ospf_data),
        }[data_plugin]

        # compose filename and make sure out folders are created
        filename = kwargs.pop("filename", f"./diagrams/{data_plugin}_{ctime}.{ext}")
        out_folder, out_filename = os.path.split(filename)
        out_folder = out_folder or "."
        os.makedirs(out_folder, exist_ok=True)

        # form list of platforms to collect output for
        n2g_supported_platorms = [
            ".".join(i.split(".")[:-1])
            for i in list_ttp_templates()["misc"]["N2G"][template_dir]
        ]
        # if FM filter provided, leave only supported platforms
        platforms = set(
            [p for p in n2g_supported_platorms if any(fnmatchcase(p, fm) for fm in FM)]
            if FM
            else n2g_supported_platorms
        )

        # retrieve output on a per-platform basis
        for platform in platforms:
            n2g_data.setdefault(platform, [])
            cli_kwargs = copy.deepcopy(kwargs)
            cli_kwargs["FM"] = [platform]
            cli_kwargs["enable"] = True
            # use N2G ttp templates to get list of commands
            parser = ttp(
                template=f"ttp://misc/N2G/{template_dir}/{platform}.txt",
                log_level="CRITICAL",
            )
            ttp_inputs_load = parser.get_input_load()
            for template_name, inputs in ttp_inputs_load.items():
                for input_name, input_params in inputs.items():
                    cli_kwargs["commands"] = input_params["commands"]
            # collect commands output from devices
            job_results = NFCLIENT.run_job(
                "nornir",
                "cli",
                workers=workers,
                kwargs=cli_kwargs,
                uuid=uuid,
                timeout=timeout,
            )
            # populate n2g data dictionary keyed by platform and save results to files
            for worker, results in job_results.items():
                if results["failed"]:
                    log.error(f"{worker} failed to collect output")
                    continue
                for host_name, host_result in results["result"].items():
                    n2g_data[platform].append("\n".join(host_result.values()))
                    hosts_processed.add(host_name)

        # create, populate and save diagram
        try:
            drawing = drawing_plugin()
            drawer = n2g_data_plugin(drawing, **n2g_kwargs)
            drawer.work(n2g_data)
            drawing.dump_file(folder=out_folder, filename=out_filename)

            return (
                f" diagram: '{data_plugin}', format: '{diagram_plugin}'\n"
                f" saved at: '{os.path.join(out_folder, out_filename)}'\n"
                f" hosts: {', '.join(list(sorted(hosts_processed)))}"
            )
        except Exception as e:
            return (
                f" Failed to produce diagram, '{data_plugin}' data plugin, "
                f"'{diagram_plugin}' diagram plugin, error: '{e}'"
            )

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir-diagram]#"
