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
from nornir_salt.plugins.functions import TabulateFormatter

NFCLIENT = None  # NFCLIENT updated by parent shell
RICHCONSOLE = Console()
SERVICE = "nornir"
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------------------------


def print_stats(data: dict):
    for k, v in data.items():
        print(f" {k}: {v}")


def print_nornir_results(data: Union[list, dict]):
    """
    Pretty print Nornir task results.

    Order of output is deterministic - same tasks will be printed in same
    order no matter how many times they are run thanks to sing ``sorted``
    """
    indent = "    "

    # print text data e.g. tabulate table
    if not isinstance(data, dict):
        RICHCONSOLE.print(data)
        return

    # iterate over Nornir results dictionary, unpack and pretty print it
    for worker in sorted(data.keys()):
        hosts_results = data[worker]
        if isinstance(hosts_results, dict):
            for host in sorted(hosts_results.keys()):
                tasks = hosts_results[host]
                RICHCONSOLE.print(f"[bold green]{host}[/bold green]:")
                for task in sorted(tasks.keys()):
                    result = tasks[task]
                    RICHCONSOLE.print(f"{1*indent}[bold blue]{task}[/bold blue]:")
                    if isinstance(result, str):
                        for line in result.splitlines():
                            print(f"{2*indent}{line}")
                    elif isinstance(result, dict):
                        for k, v in result.items():
                            lines = str(v).splitlines()
                            if len(lines) == 0:
                                RICHCONSOLE.print(
                                    f"{2*indent}[bold yellow]{k}[/bold yellow]: ''"
                                )
                            elif len(lines) == 1:
                                RICHCONSOLE.print(
                                    f"{2*indent}[bold yellow]{k}[/bold yellow]: {lines[0]}"
                                )
                            else:
                                RICHCONSOLE.print(
                                    f"{2*indent}[bold yellow]{k}[/bold yellow]"
                                )
                                for line in lines:
                                    print(f"{3*indent}{line}")
                    elif isinstance(result, list):
                        for i in result:
                            if i.strip().splitlines():  # multiline
                                for line in i.strip().splitlines():
                                    RICHCONSOLE.print(
                                        f"{2*indent}[bold yellow]{line}[/bold yellow]"
                                    )
                            else:
                                RICHCONSOLE.print(
                                    f"{2*indent}[bold yellow]{i.strip()}[/bold yellow]"
                                )
        # handle to_dict is False
        elif isinstance(hosts_results, list):
            print(hosts_results)


# ---------------------------------------------------------------------------------------------
# SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


class EnumTableTypes(str, Enum):
    table_brief = "brief"
    table_terse = "terse"
    table_extend = "extend"


class TabulateTableModel(BaseModel):
    table: Union[EnumTableTypes, Dict, StrictBool] = Field(
        None, description="table format or parameters", presence="brief"
    )
    headers: Union[StrictStr, List[StrictStr]] = Field(
        None, description="table headers"
    )
    headers_exclude: Union[StrictStr, List[StrictStr]] = Field(
        None, description="table headers to exclude"
    )
    sortby: StrictStr = Field(None, description="table header column to sort by")
    reverse: StrictBool = Field(
        None, description="table reverse the sort by order", presence=True
    )


class filters(BaseModel):
    """
    Model to list common filter arguments for FFun function
    """

    FO: Optional[Union[Dict, List[Dict]]] = Field(
        None, title="Filter Object", description="Filter hosts using Filter Object"
    )
    FB: Optional[Union[List[str], str]] = Field(
        None,
        title="Filter gloB",
        description="Filter hosts by name using Glob Patterns",
    )
    FH: Optional[Union[List[StrictStr], StrictStr]] = Field(
        None, title="Filter Hostname", description="Filter hosts by hostname"
    )
    FC: Optional[Union[List[str], str]] = Field(
        None,
        title="Filter Contains",
        description="Filter hosts containment of pattern in name",
    )
    FR: Optional[Union[List[str], str]] = Field(
        None,
        title="Filter Regex",
        description="Filter hosts by name using Regular Expressions",
    )
    FG: Optional[StrictStr] = Field(
        None, title="Filter Group", description="Filter hosts by group"
    )
    FP: Optional[Union[List[StrictStr], StrictStr]] = Field(
        None,
        title="Filter Prefix",
        description="Filter hosts by hostname using IP Prefix",
    )
    FL: Optional[Union[List[StrictStr], StrictStr]] = Field(
        None, title="Filter List", description="Filter hosts by names list"
    )
    FM: Optional[Union[List[StrictStr], StrictStr]] = Field(
        None, title="Filter platforM", description="Filter hosts by platform"
    )
    FX: Optional[Union[List[str], str]] = Field(
        None, title="Filter eXclude", description="Filter hosts excluding them by name"
    )
    FN: Optional[StrictBool] = Field(
        None, title="Filter Negate", description="Negate the match"
    )
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Filter worker to target"
    )
    hosts: Union[StrictStr, List[StrictStr]] = Field(
        None, description="Filter hosts to target"
    )

    @staticmethod
    def source_workers():
        reply = NFCLIENT.get("mmi.service.broker", "show_workers")
        reply = json.loads(reply)
        return [w["name"] for w in reply if w["service"].startswith("nornir")]

    @staticmethod
    def source_hosts():
        ret = set()
        reply = NFCLIENT.run_job("nornir", "get_nornir_hosts")
        # reply is a dict keyed by worker name with lists of hosts values
        for worker, hosts in reply.items():
            for host in hosts:
                ret.add(host)
        return list(ret)

    @staticmethod
    def source_FL():
        return filters.source_hosts()

    @staticmethod
    def get_nornir_hosts(**kwargs):
        workers = kwargs.pop("workers", "all")
        reply = NFCLIENT.run_job(
            "nornir", "get_nornir_hosts", workers=workers, kwargs=kwargs
        )
        try:
            if isinstance(reply, (bytes, str)):
                return json.dumps(json.loads(reply), indent=4)
            else:
                return reply
        except Exception as e:
            log.error(
                f"failed to deserialise JSON reply, reply content '{reply}', error '{e}'"
            )


class NornirShowCommandsModel(filters):
    inventory: Callable = Field(
        "get_nornir_inventory",
        description="show Nornir inventory data",
    )
    hosts: Callable = Field(
        "print_nornir_hosts",
        description="show Nornir hosts",
    )
    version: Callable = Field(
        "print_nornir_version",
        description="show Nornir service version report",
    )

    class PicleConfig:
        outputter = Outputters.outputter_rich_json
        pipe = PipeFunctionsModel

    @staticmethod
    def get_nornir_inventory(**kwargs):
        workers = kwargs.pop("workers", "all")
        return NFCLIENT.run_job("nornir", "get_nornir_inventory", workers=workers)

    @staticmethod
    def print_nornir_hosts(**kwargs):
        return filters.get_nornir_hosts(**kwargs)

    @staticmethod
    def print_nornir_version(**kwargs):
        workers = kwargs.pop("workers", "all")
        return NFCLIENT.run_job("nornir", "get_nornir_version", workers=workers)


# ---------------------------------------------------------------------------------------------
# CLI SHELL NORNIR SERVICE MODELS
# ---------------------------------------------------------------------------------------------


class NrCliPlugins(str, Enum):
    netmiko = "netmiko"
    napalm = "napalm"
    scrapli = "scrapli"


class NrCfgPlugins(str, Enum):
    netmiko = "netmiko"
    napalm = "napalm"
    scrapli = "scrapli"


class NornirCliShell(filters, TabulateTableModel):
    commands: Optional[Union[StrictStr, List[StrictStr]]] = Field(
        None, description="List of commands to collect form devices"
    )
    plugin: NrCliPlugins = Field("netmiko", description="Connection plugin name")
    add_details: Optional[StrictBool] = Field(
        False,
        description="Add task details to results",
        json_schema_extra={"presence": True},
    )
    to_dict: Optional[StrictBool] = Field(
        True, description="Control task results structure"
    )
    dry_run: Optional[StrictBool] = Field(
        None, description="Dry run the commands", json_schema_extra={"presence": True}
    )
    enable: Optional[StrictBool] = Field(
        None, description="Enter exec mode", json_schema_extra={"presence": True}
    )

    @staticmethod
    def run(*args, **kwargs):
        workers = kwargs.pop("workers", "all")

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
        # first_done = False
        # for reply in NFCLIENT.run_job_iter("nornir", "cli", workers=workers, args=args, kwargs=kwargs):
        #     if first_done is False:
        #         print(f"Submitted job to workers {', '.join(reply['workers'])}")
        #         first_done = True
        #     else:
        #         print(f"Received job results")
        #         print_nornir_results(reply)
        with RICHCONSOLE.status(
            "[bold green]Collecting CLI commands", spinner="dots"
        ) as status:
            result = NFCLIENT.run_job(
                "nornir", "cli", workers=workers, args=args, kwargs=kwargs
            )

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

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir-cli]#"
        outputter = print_nornir_results


class NornirServiceCommands(BaseModel):
    cli: NornirCliShell = Field(None, description="Send CLI commands to devices")
    show: NornirShowCommandsModel = Field(None, description="nornir data")

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir]#"
