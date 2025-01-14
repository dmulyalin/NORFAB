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
from nornir_salt.plugins.functions import TabulateFormatter


class EnumTableTypes(str, Enum):
    table_brief = "brief"
    table_terse = "terse"
    table_extend = "extend"


class NornirTestShell(
    NorniHostsFilters, TabulateTableModel, NornirCommonArgs, ClientRunJobArgs
):
    suite: StrictStr = Field(
        ..., description="Nornir suite nf://path/to/file.py", required=True
    )
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
    job_data: Optional[StrictStr] = Field(
        None, description="Path to YAML file with job data"
    )
    table: Union[EnumTableTypes, Dict, StrictBool] = Field(
        "brief",
        description="Table format (brief, terse, extend) or parameters or True",
        presence="brief",
    )

    @staticmethod
    def source_suite():
        broker_files = reply = NFCLIENT.get(
            "fss.service.broker", "walk", kwargs={"url": "nf://"}
        )
        return json.loads(broker_files["results"])

    @staticmethod
    def source_job_data():
        broker_files = reply = NFCLIENT.get(
            "fss.service.broker", "walk", kwargs={"url": "nf://"}
        )
        return json.loads(broker_files["results"])

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)

        # extract job_data
        if kwargs.get("job_data"):
            kwargs["job_data"] = json.loads(kwargs["job_data"])
            
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
            "test",
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
        prompt = "nf[nornir-test]#"
        outputter = print_nornir_results
