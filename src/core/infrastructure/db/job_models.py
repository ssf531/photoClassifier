import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from core.infrastructure.db.base import HasId, UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration


class Job(HasId):
    __tablename__ = "job"

    job_type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow, onupdate=_utcnow)


class JobItem(HasId):
    __tablename__ = "job_item"
    __table_args__ = (
        Index("ix_job_item_job_status", "job_id", "status"),
        Index("ix_job_item_error_code", "error_code"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("job.id"))
    file_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)
    ignored_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
