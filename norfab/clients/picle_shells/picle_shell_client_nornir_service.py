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
        data = data.replace("FAIL", "[bold red]FAIL[/bold red]")
        data = data.replace("PASS", "[bold green]PASS[/bold green]")
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
                            if isinstance(i, str):
                                if i.strip().splitlines():  # multiline
                                    for line in i.strip().splitlines():
                                        RICHCONSOLE.print(
                                            f"{2*indent}[bold yellow]{line}[/bold yellow]"
                                        )
                                else:
                                    RICHCONSOLE.print(
                                        f"{2*indent}[bold yellow]{i.strip()}[/bold yellow]"
                                    )
                            elif isinstance(
                                i,
                                (
                                    dict,
                                    list,
                                ),
                            ):
                                for line in json.dumps(
                                    result, indent=indent
                                ).splitlines():
                                    RICHCONSOLE.print(
                                        f"{2*indent}[bold yellow]{line}[/bold yellow]"
                                    )
                                break  # we printed full result, stop
                            else:
                                RICHCONSOLE.print(
                                    f"{2*indent}[bold yellow]{result}[/bold yellow]"
                                )
                    else:
                        RICHCONSOLE.print(
                            f"{2*indent}[bold yellow]{result}[/bold yellow]"
                        )
        # handle to_dict is False
        elif isinstance(hosts_results, list):
            print(hosts_results)


# ---------------------------------------------------------------------------------------------
# COMMON MODELS
# ---------------------------------------------------------------------------------------------


class NornirCommonArgs(BaseModel):
    add_details: Optional[StrictBool] = Field(
        False,
        description="Add task details to results",
        json_schema_extra={"presence": True},
    )
    run_num_workers: Optional[StrictInt] = Field(
        None, description="RetryRunner number of threads for tasks execution"
    )
    run_num_connectors: Optional[StrictInt] = Field(
        None, description="RetryRunner number of threads for device connections"
    )
    run_connect_retry: Optional[StrictInt] = Field(
        None, description="RetryRunner number of connection attempts"
    )
    run_task_retry: Optional[StrictInt] = Field(
        None, description="RetryRunner number of attempts to run task"
    )
    run_reconnect_on_fail: Optional[StrictBool] = Field(
        None,
        description="RetryRunner perform reconnect to host on task failure",
        json_schema_extra={"presence": True},
    )
    run_creds_retry: Optional[List] = Field(
        None,
        description="RetryRunner ist of connection credentials and parameters to retry",
    )


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


# ---------------------------------------------------------------------------------------------
# NORNIR SERVICE SHELL SHOW COMMANDS MODELS
# ---------------------------------------------------------------------------------------------


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
        "get_nornir_version",
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
    def get_nornir_version(**kwargs):
        workers = kwargs.pop("workers", "all")
        return NFCLIENT.run_job("nornir", "get_nornir_version", workers=workers)


# ---------------------------------------------------------------------------------------------
# CLI SHELL NORNIR SERVICE MODELS
# ---------------------------------------------------------------------------------------------


class NrCliPluginNetmiko(BaseModel):
    # nornir_netmiko.tasks.netmiko_send_command arguments
    enable: Optional[StrictBool] = Field(
        None,
        description="Attempt to enter enable-mode",
        json_schema_extra={"presence": True},
    )
    use_timing: Optional[StrictBool] = Field(
        None,
        description="switch to send command timing method",
        json_schema_extra={"presence": True},
    )
    # netmiko send_command methos arguments
    expect_string: Optional[StrictStr] = Field(
        None,
        description="Regular expression pattern to use for determining end of output",
    )
    read_timeout: Optional[StrictInt] = Field(
        None, description="Maximum time to wait looking for pattern"
    )
    auto_find_prompt: Optional[StrictBool] = Field(
        None, description="Use find_prompt() to override base prompt"
    )
    strip_prompt: Optional[StrictBool] = Field(
        None,
        description="Remove the trailing router prompt from the output",
        json_schema_extra={"presence": True},
    )
    strip_command: Optional[StrictBool] = Field(
        None,
        description="Remove the echo of the command from the output",
        json_schema_extra={"presence": True},
    )
    normalize: Optional[StrictBool] = Field(
        None,
        description="Ensure the proper enter is sent at end of command",
        json_schema_extra={"presence": True},
    )
    use_textfsm: Optional[StrictBool] = Field(
        None,
        description="Process command output through TextFSM template",
        json_schema_extra={"presence": True},
    )
    textfsm_template: Optional[StrictStr] = Field(
        None,
        description="Name of template to parse output with",
    )
    use_ttp: Optional[StrictBool] = Field(
        None,
        description="Process command output through TTP template",
        json_schema_extra={"presence": True},
    )
    ttp_template: Optional[StrictBool] = Field(
        None,
        description="Name of template to parse output with",
    )
    use_genie: Optional[StrictBool] = Field(
        None,
        description="Process command output through PyATS/Genie parser",
        json_schema_extra={"presence": True},
    )
    cmd_verify: Optional[StrictBool] = Field(
        None,
        description="Verify command echo before proceeding",
        json_schema_extra={"presence": True},
    )
    # nornir_salt.plugins.tasks.netmiko_send_commands arguments
    interval: Optional[StrictInt] = Field(
        None,
        description="Interval between sending commands",
    )
    use_ps: Optional[StrictBool] = Field(
        None,
        description="Use send command promptless method",
        json_schema_extra={"presence": True},
    )
    split_lines: Optional[StrictBool] = Field(
        None,
        description="Split multiline string to individual commands",
        json_schema_extra={"presence": True},
    )
    new_line_char: Optional[StrictStr] = Field(
        None,
        description="Character to replace with new line before sending to device, default is _br_",
    )
    repeat: Optional[StrictInt] = Field(
        None,
        description="Number of times to repeat the commands",
    )
    stop_pattern: Optional[StrictStr] = Field(
        None,
        description="Stop commands repeat if output matches provided glob pattern",
    )
    repeat_interval: Optional[StrictInt] = Field(
        None,
        description="Time in seconds to wait between repeating commands",
    )
    return_last: Optional[StrictInt] = Field(
        None,
        description="Returns requested last number of commands outputs",
    )

    @staticmethod
    def run(*args, **kwargs):
        kwargs["plugin"] = "netmiko"
        return NornirCliShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = print_nornir_results


class NrCliPluginScrapli(BaseModel):
    # nornir_scrapli.tasks.send_command arguments
    strip_prompt: Optional[StrictBool] = Field(
        None,
        description="Strip prompt from returned output",
        json_schema_extra={"presence": True},
    )
    failed_when_contains: Optional[StrictStr] = Field(
        None,
        description="String or list of strings indicating failure if found in response",
    )
    timeout_ops: Optional[StrictInt] = Field(
        None,
        description="Timeout ops value for this operation",
    )
    # nornir_salt.plugins.tasks.scrapli_send_commands arguments
    interval: Optional[StrictInt] = Field(
        None,
        description="Interval between sending commands",
    )
    split_lines: Optional[StrictBool] = Field(
        None,
        description="Split multiline string to individual commands",
        json_schema_extra={"presence": True},
    )
    new_line_char: Optional[StrictStr] = Field(
        None,
        description="Character to replace with new line before sending to device, default is _br_",
    )
    repeat: Optional[StrictInt] = Field(
        None,
        description="Number of times to repeat the commands",
    )
    stop_pattern: Optional[StrictStr] = Field(
        None,
        description="Stop commands repeat if output matches provided glob pattern",
    )
    repeat_interval: Optional[StrictInt] = Field(
        None,
        description="Time in seconds to wait between repeating commands",
    )
    return_last: Optional[StrictInt] = Field(
        None,
        description="Returns requested last number of commands outputs",
    )

    @staticmethod
    def run(*args, **kwargs):
        kwargs["plugin"] = "scrapli"
        return NornirCliShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = print_nornir_results


class NrCliPluginNapalm(BaseModel):
    # nornir_salt.plugins.tasks.napalm_send_commands arguments
    interval: Optional[StrictInt] = Field(
        None,
        description="Interval between sending commands",
    )
    split_lines: Optional[StrictBool] = Field(
        None,
        description="Split multiline string to individual commands",
        json_schema_extra={"presence": True},
    )
    new_line_char: Optional[StrictStr] = Field(
        None,
        description="Character to replace with new line before sending to device, default is _br_",
    )

    @staticmethod
    def run(*args, **kwargs):
        kwargs["plugin"] = "napalm"
        return NornirCliShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = print_nornir_results


class NrCliPlugins(BaseModel):
    netmiko: NrCliPluginNetmiko = Field(
        None, description="Use Netmiko plugin to configure devices"
    )
    scrapli: NrCliPluginScrapli = Field(
        None, description="Use Scrapli plugin to configure devices"
    )
    napalm: NrCliPluginNapalm = Field(
        None, description="Use NAPALM plugin to configure devices"
    )


class NornirCliShell(filters, TabulateTableModel, NornirCommonArgs):
    commands: Optional[Union[StrictStr, List[StrictStr]]] = Field(
        None,
        description="List of commands to collect form devices",
        json_schema_extra={"multiline": True},
    )
    plugin: NrCliPlugins = Field(None, description="Connection plugin parameters")
    cli_dry_run: Optional[StrictBool] = Field(
        None, description="Dry run the commands", json_schema_extra={"presence": True}
    )
    enable: Optional[StrictBool] = Field(
        None, description="Enter exec mode", json_schema_extra={"presence": True}
    )
    run_ttp: Optional[StrictStr] = Field(None, description="TTP Template to run")

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


# ---------------------------------------------------------------------------------------------
# CFG SHELL NORNIR SERVICE MODELS
# ---------------------------------------------------------------------------------------------


class NrCfgPluginNetmiko(BaseModel):
    enable: Optional[StrictBool] = Field(
        None,
        description="Attempt to enter enable-mode",
        json_schema_extra={"presence": True},
    )
    exit_config_mode: Optional[StrictBool] = Field(
        None,
        description="Determines whether or not to exit config mode after complete",
        json_schema_extra={"presence": True},
    )
    strip_prompt: Optional[StrictBool] = Field(
        None,
        description="Determines whether or not to strip the prompt",
        json_schema_extra={"presence": True},
    )
    strip_command: Optional[StrictBool] = Field(
        None,
        description="Determines whether or not to strip the command",
        json_schema_extra={"presence": True},
    )
    read_timeout: Optional[StrictInt] = Field(
        None, description="Absolute timer to send to read_channel_timing"
    )
    config_mode_command: Optional[StrictStr] = Field(
        None, description="The command to enter into config mode"
    )
    cmd_verify: Optional[StrictBool] = Field(
        None,
        description="Whether or not to verify command echo for each command in config_set",
        json_schema_extra={"presence": True},
    )
    enter_config_mode: Optional[StrictBool] = Field(
        None,
        description="Do you enter config mode before sending config commands",
        json_schema_extra={"presence": True},
    )
    error_pattern: Optional[StrictStr] = Field(
        None,
        description="Regular expression pattern to detect config errors in the output",
    )
    terminator: Optional[StrictStr] = Field(
        None, description="Regular expression pattern to use as an alternate terminator"
    )
    bypass_commands: Optional[StrictStr] = Field(
        None,
        description="Regular expression pattern indicating configuration commands, cmd_verify is automatically disabled",
    )
    commit: Optional[Union[StrictBool, dict]] = Field(
        None,
        description="Commit configuration or not or dictionary with commit parameters",
        json_schema_extra={"presence": True},
    )
    commit_final_delay: Optional[StrictInt] = Field(
        None, description="Time to wait before doing final commit"
    )
    batch: Optional[StrictInt] = Field(
        None, description="Commands count to send in batches"
    )

    @staticmethod
    def run(*args, **kwargs):
        kwargs["plugin"] = "netmiko"
        return NornirCfgShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = print_nornir_results


class NrCfgPluginScrapli(BaseModel):
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Apply changes or not, also tests if possible to enter config mode",
        json_schema_extra={"presence": True},
    )
    strip_prompt: Optional[StrictBool] = Field(
        None,
        description="Strip prompt from returned output",
        json_schema_extra={"presence": True},
    )
    failed_when_contains: Optional[StrictStr] = Field(
        None,
        description="String or list of strings indicating failure if found in response",
    )
    stop_on_failed: Optional[StrictBool] = Field(
        None,
        description="Stop executing commands if command fails",
        json_schema_extra={"presence": True},
    )
    privilege_level: Optional[StrictStr] = Field(
        None,
        description="Name of configuration privilege level to acquire",
    )
    eager: Optional[StrictBool] = Field(
        None,
        description="Do not read until prompt is seen at each command sent to the channel",
        json_schema_extra={"presence": True},
    )
    timeout_ops: Optional[StrictInt] = Field(
        None,
        description="Timeout ops value for this operation",
    )

    @staticmethod
    def run(*args, **kwargs):
        kwargs["plugin"] = "scrapli"
        return NornirCfgShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = print_nornir_results


class NrCfgPluginNapalm(BaseModel):
    replace: Optional[StrictBool] = Field(
        None,
        description="Whether to replace or merge the configuration",
        json_schema_extra={"presence": True},
    )
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Apply changes or not, also tests if possible to enter config mode",
        json_schema_extra={"presence": True},
    )
    revert_in: Optional[StrictInt] = Field(
        None,
        description="Amount of time in seconds after which to revert the commit",
    )

    @staticmethod
    def run(*args, **kwargs):
        kwargs["plugin"] = "napalm"
        return NornirCfgShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = print_nornir_results


class NrCfgPlugins(BaseModel):
    netmiko: NrCfgPluginNetmiko = Field(
        None, description="Use Netmiko plugin to configure devices"
    )
    scrapli: NrCfgPluginScrapli = Field(
        None, description="Use Scrapli plugin to configure devices"
    )
    napalm: NrCfgPluginNapalm = Field(
        None, description="Use NAPALM plugin to configure devices"
    )


class NornirCfgShell(filters, TabulateTableModel, NornirCommonArgs):
    cfg_dry_run: Optional[StrictBool] = Field(
        None, description="Dry run cfg function", json_schema_extra={"presence": True}
    )
    config: Optional[Union[StrictStr, List[StrictStr]]] = Field(
        None,
        description="List of configuration commands to send to devices",
        json_schema_extra={"multiline": True},
    )
    plugin: NrCfgPlugins = Field(None, description="Configuration plugin parameters")

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
        with RICHCONSOLE.status(
            "[bold green]Configuring devices", spinner="dots"
        ) as status:
            result = NFCLIENT.run_job(
                "nornir", "cfg", workers=workers, args=args, kwargs=kwargs
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
        with RICHCONSOLE.status(
            "[bold green]Configuring devices", spinner="dots"
        ) as status:
            result = NFCLIENT.run_job(
                "nornir", "cfg", workers=workers, args=args, kwargs=kwargs
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
        prompt = "nf[nornir-cfg]#"
        outputter = print_nornir_results


# ---------------------------------------------------------------------------------------------
# NORNIR SERVICE TASK SHELL MODEL
# ---------------------------------------------------------------------------------------------


class NornirTaskShell(filters, TabulateTableModel, NornirCommonArgs):
    plugin: StrictStr = Field(
        None,
        description="Nornir task.plugin.name to import or nf://path/to/plugin/file.py",
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
        with RICHCONSOLE.status("[bold green]Running task", spinner="dots") as status:
            result = NFCLIENT.run_job(
                "nornir", "task", workers=workers, args=args, kwargs=kwargs
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
        prompt = "nf[nornir-task]#"
        outputter = print_nornir_results


# ---------------------------------------------------------------------------------------------
# NORNIR SERVICE TEST SHELL MODEL
# ---------------------------------------------------------------------------------------------


class NornirTestShell(filters, TabulateTableModel, NornirCommonArgs):
    suite: StrictStr = Field(None, description="Nornir suite nf://path/to/file.py")
    dry_run: Optional[StrictBool] = Field(
        None,
        description="Return produced per-host tests suite content without running tests",
        json_schema_extra={"presence": True},
    )
    subset: Optional[StrictStr] = Field(
        None,
        description="Filter tests by name",
    )
    failed_only: Optional[StrictBool] = Field(
        None,
        description="Return test results for failed tests only",
        json_schema_extra={"presence": True},
    )
    remove_tasks: Optional[StrictBool] = Field(
        None,
        description="Include/Exclude tested task results",
        json_schema_extra={"presence": True},
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
        with RICHCONSOLE.status("[bold green]Running tests", spinner="dots") as status:
            result = NFCLIENT.run_job(
                "nornir", "test", workers=workers, args=args, kwargs=kwargs
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
        prompt = "nf[nornir-test]#"
        outputter = print_nornir_results


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

    # netconf:
    # file:
    # gnmi:
    # snmp:
    # net:
    # netbox:
    # inventory:

    show: NornirShowCommandsModel = Field(
        None, description="Show Nornir service parameters"
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir]#"
