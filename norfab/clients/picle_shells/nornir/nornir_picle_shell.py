"""
PICLE Shell CLient
==================

Client that implements interactive shell to work with NorFab.
"""
import logging

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
from .nornir_picle_shell_cli import NornirCliShell
from .nornir_picle_shell_cfg import NornirCfgShell
from .nornir_picle_shell_task import NornirTaskShell
from .nornir_picle_shell_parse import NornirParseShell
from .nornir_picle_shell_test import NornirTestShell
from .nornir_picle_shell_network import NornirNetworkShell
from .nornir_picle_shell_diagram import NornirDiagramShell
from typing import Union, Optional, List, Any, Dict, Callable, Tuple
from nornir_salt.plugins.functions import TabulateFormatter

SERVICE = "nornir"
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# NORNIR SERVICE SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class NornirShowHostsModel(NorniHostsFilters, TabulateTableModel):
    details: Optional[StrictBool] = Field(
        None, description="show hosts details", presence=True
    )

    class PicleConfig:
        outputter = Outputters.outputter_rich_json
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args, **kwargs):
        # extract Tabulate arguments
        table = kwargs.pop("table", {})  # tabulate
        headers = kwargs.pop("headers", "keys")  # tabulate
        headers_exclude = kwargs.pop("headers_exclude", [])  # tabulate
        sortby = kwargs.pop("sortby", "host")  # tabulate
        reverse = kwargs.pop("reverse", False)  # tabulate

        # run task
        result = NorniHostsFilters.get_nornir_hosts(**kwargs)

        # form table results
        if table:
            if table is True or table == "brief":
                table = {"tablefmt": "grid"}
            table_data = []
            for w_name, w_res in result.items():
                if isinstance(w_res, list):
                    for item in w_res:
                        table_data.append({"worker": w_name, "host": item})
                elif isinstance(w_res, dict):
                    for host, host_data in w_res.items():
                        table_data.append({"worker": w_name, "host": host, **host_data})
                else:
                    return result
            ret = (  # tuple to return outputter reference
                TabulateFormatter(
                    table_data,
                    tabulate=table,
                    headers=headers,
                    headers_exclude=headers_exclude,
                    sortby=sortby,
                    reverse=reverse,
                ),
                Outputters.outputter_rich_print,
            )
        else:
            ret = result

        return ret


class ShowWatchDogModel(NorniHostsFilters):
    statistics: Callable = Field(
        "get_watchdog_stats",
        description="show Nornir watchdog statistics",
    )
    configuration: Callable = Field(
        "get_watchdog_configuration",
        description="show Nornir watchdog configuration",
    )
    connections: Callable = Field(
        "get_watchdog_connections",
        description="show Nornir watchdog connections monitoring data",
    )

    class PicleConfig:
        outputter = Outputters.outputter_rich_json

    @staticmethod
    def get_watchdog_stats(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("nornir", "get_watchdog_stats", workers=workers)
        return log_error_or_result(result)

    @staticmethod
    def get_watchdog_configuration(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job(
            "nornir", "get_watchdog_configuration", workers=workers
        )
        return log_error_or_result(result)

    @staticmethod
    def get_watchdog_connections(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("nornir", "get_watchdog_connections", workers=workers)
        return log_error_or_result(result)


class NornirShowInventoryModel(NorniHostsFilters, ClientRunJobArgs):
    class PicleConfig:
        outputter = Outputters.outputter_rich_json
        pipe = PipeFunctionsModel

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)

        if kwargs.get("hosts"):
            kwargs["FL"] = kwargs.pop("hosts")

        result = NFCLIENT.run_job(
            "nornir",
            "get_nornir_inventory",
            kwargs=kwargs,
            workers=workers,
            timeout=timeout,
        )
        return log_error_or_result(result)


class NornirShowCommandsModel(BaseModel):
    inventory: NornirShowInventoryModel = Field(
        None,
        description="show Nornir inventory data",
    )
    hosts: NornirShowHostsModel = Field(
        "print_nornir_hosts",
        description="show Nornir hosts",
    )
    version: Callable = Field(
        "get_nornir_version",
        description="show Nornir service version report",
    )
    watchdog: ShowWatchDogModel = Field(
        None,
        description="show Nornir service version report",
    )

    class PicleConfig:
        outputter = Outputters.outputter_rich_json
        pipe = PipeFunctionsModel

    @staticmethod
    def get_nornir_version(**kwargs):
        workers = kwargs.pop("workers", "all")
        result = NFCLIENT.run_job("nornir", "get_nornir_version", workers=workers)
        return log_error_or_result(result)


# ---------------------------------------------------------------------------------------------
# NORNIR SERVICE MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class NornirServiceCommands(BaseModel):
    cli: NornirCliShell = Field(None, description="Send CLI commands to devices")
    cfg: NornirCfgShell = Field(
        None, description="Configure devices over CLI interface"
    )
    task: NornirTaskShell = Field(None, description="Run Nornir task")
    test: NornirTestShell = Field(None, description="Run network tests")
    network: NornirNetworkShell = Field(
        None, description="Network utility functions - ping, dns etc."
    )
    parse: NornirParseShell = Field(None, description="Parse network devices output")
    diagram: NornirDiagramShell = Field(None, description="Produce network diagrams")

    # netconf:
    # file:
    # gnmi:
    # snmp:
    # inventory:

    show: NornirShowCommandsModel = Field(
        None, description="Show Nornir service parameters"
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir]#"
