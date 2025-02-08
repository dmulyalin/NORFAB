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
    running = "running"
    completed = "completed"
    failed = "failed"
    unknown = "unknown"


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


# ------------------------------------------------------
# NorFab Response Models
# ------------------------------------------------------


class WorkerResult(BaseModel):
    errors: List[StrictStr] = Field(..., mandatory=True)
    failed: StrictBool = Field(..., mandatory=True)
    juuid: StrictStr = Field(..., mandatory=True)
    messages: List[StrictStr] = Field(..., mandatory=True)
    result: Any = Field(..., mandatory=True)


class ClientPostJobResponse(BaseModel):
    errors: List[StrictStr] = Field(..., mandatory=True)
    status: StrictStr = Field(..., mandatory=True)
    uuid: StrictStr = Field(..., mandatory=True)
    workers: List[StrictStr] = Field(..., mandatory=True)


class ClientGetJobWorkers(BaseModel):
    dispatched: List[StrictStr] = Field(..., mandatory=True)
    done: List[StrictStr] = Field(..., mandatory=True)
    pending: List[StrictStr] = Field(..., mandatory=True)
    requested: StrictStr = Field(..., mandatory=True)


class ClientGetJobResponse(BaseModel):
    errors: List[StrictStr] = Field(..., mandatory=True)
    status: StrictStr = Field(..., mandatory=True)
    workers: ClientGetJobWorkers = Field(..., mandatory=True)
    results: Dict[StrictStr, WorkerResult] = Field(..., mandatory=True)
