import json

from typing import Optional
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
from nornir_salt.plugins.functions import TabulateFormatter


class SCPDirection(str, Enum):
    put = "put"
    get = "get"


class NrFileCopyPluginNetmiko(BaseModel):
    dest_file: StrictStr = Field(
        None, description="Destination file to copy", alias="dest-file"
    )
    file_system: StrictStr = Field(
        None, description="Destination file system", alias="file-system"
    )
    direction: SCPDirection = Field("put", description="Direction of file copy")
    inline_transfer: StrictBool = Field(
        False,
        description="Use inline transfer, supported by Cisco IOS",
        alias="inline-transfer",
        json_schema_extra={"presence": True},
    )
    overwrite_file: StrictBool = Field(
        False,
        description="Overwrite destination file if it exists",
        alias="overwrite-file",
        json_schema_extra={"presence": True},
    )
    socket_timeout: StrictFloat = Field(
        10.0, description="Socket timeout in seconds", alias="socket-timeout"
    )
    verify_file: StrictBool = Field(
        True,
        description="Verify destination file hash after copy",
        alias="verify-file",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    def run(*args, **kwargs):
        kwargs["plugin"] = "netmiko"
        return NornirFileCopyShell.run(*args, **kwargs)

    class PicleConfig:
        outputter = print_nornir_results


class NrFileCopyPlugins(BaseModel):
    netmiko: NrFileCopyPluginNetmiko = Field(
        None, description="Use Netmiko plugin to copy files"
    )


class NornirFileCopyShell(
    NorniHostsFilters, TabulateTableModel, NornirCommonArgs, ClientRunJobArgs
):
    source_file: StrictStr = Field(
        ..., description="Source file to copy", mandatory=True
    )
    plugin: NrFileCopyPlugins = Field(None, description="Connection plugin parameters")
    dry_run: StrictBool = Field(
        False,
        description="Do not copy files, just show what would be done",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    def source_source_file():
        broker_files = NFCLIENT.get(
            "fss.service.broker", "walk", kwargs={"url": "nf://"}
        )
        return broker_files["results"]

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)

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
            "file_copy",
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

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir-file-copy]#"
        outputter = print_nornir_results
