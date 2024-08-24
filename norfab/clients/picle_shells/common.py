"""
Common Pydantic Models for PICLE Client Shells
"""
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

class ClientRunJobArgs(BaseModel):
    job_timeout: Optional[StrictInt] = Field(None, description="Job timeout")
    workers: Union[StrictStr, List[StrictStr]] = Field(
        "all", description="Filter worker to target"
    )
    