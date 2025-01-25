from pydantic import (
    BaseModel,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    Field,
    model_validator,
)
from enum import Enum
from typing import Union, Optional, List, Any, Dict, Callable, Tuple
from datetime import datetime

# ------------------------------------------------------
# NorFab event models
# ------------------------------------------------------


class EventSeverityLevels(str, Enum):
    info = "INFO"
    debug = "DEBUG"
    warning = "WARNING"
    critical = "CRITICAL"


class EventStatusValues(str, Enum):
    pending = "pending"
    scheduled = "scheduled"
    started = "started"
    in_progress = "in progress"
    completed = "completed"
    failed = "failed"
    unknown = "unknown"
    running = "running"


class NorFabEvent(BaseModel):
    message: StrictStr = Field(..., mandatory=True)
    task: StrictStr = Field(None, mandatory=False)
    status: EventStatusValues = Field(EventStatusValues.running, mandatory=False)
    resource: Union[StrictStr, List[StrictStr]] = Field([], mandatory=False)
    severity: EventSeverityLevels = Field(EventSeverityLevels.info, mandatory=False)
    timestamp: Union[StrictStr] = Field(None, mandatory=False)
    extras: Dict = Field({}, mandatory=False)

    @model_validator(mode="after")
    def add_defaults(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().strftime("%d-%b-%Y %H:%M:%S.%f")[:-3]

        return self
