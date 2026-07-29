import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

JobID = uuid.UUID


class JobStatus(str, Enum):  # noqa: UP042 -- kept pre-StrEnum pending broader migration
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIALLY_COMPLETED = "partially_completed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class JobSpec:
    job_type: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JobProgress:
    job_id: JobID
    job_type: str
    status: JobStatus
    progress_pct: float


class TaskScheduler(Protocol):
    async def enqueue(self, job: JobSpec) -> JobID: ...

    async def cancel(self, job_id: JobID) -> None: ...

    def progress_stream(self) -> AsyncIterator[JobProgress]: ...
