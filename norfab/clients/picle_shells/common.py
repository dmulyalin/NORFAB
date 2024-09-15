"""
Common Pydantic Models for PICLE Client Shells
"""
import logging
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

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# COMMON FUNCTIONS
# ---------------------------------------------------------------------------------------------


def log_error_or_result(data: dict) -> dict:
    """
    Helper function to log result errors, messages or return results.

    Returns dictionary keyed by worker name with job results as a value.

    :param data: result returned bu NFPCLIENT.run_job function
    """
    ret = {}
    for w_name, w_res in data.items():
        if w_res["errors"]:
            errors = "\n".join(w_res["errors"])
            log.error(f"{w_name} '{w_res['task']}' errors:\n{errors}")
        elif w_res["messages"]:
            messages = "\n".join(w_res["messages"])
            log.info(f"{w_name} '{w_res['task']}' messages:\n{messages}")
        else:
            ret[w_name] = w_res["result"]

    return ret


# ---------------------------------------------------------------------------------------------
# COMMON MODELS
# ---------------------------------------------------------------------------------------------


class ClientRunJobArgs(BaseModel):
    job_timeout: Optional[StrictInt] = Field(None, description="Job timeout")
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Filter worker to target"
    )
