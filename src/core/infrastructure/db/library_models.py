import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.infrastructure.db.base import HasId, UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration


class LibraryRoot(HasId):
    __tablename__ = "library_root"

    path: Mapped[str] = mapped_column(String, unique=True)
    follow_symlinks: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)


class Photo(HasId):
    __tablename__ = "photo"
    __table_args__ = (
        UniqueConstraint(
            "library_root_id", "relative_path_folded", name="uq_photo_root_relpath_folded"
        ),
        Index("ix_photo_content_hash", "content_hash"),
        Index("ix_photo_status", "status"),
        Index("ix_photo_captured_at_local", "captured_at_local"),
    )

    library_root_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("library_root.id"))
    relative_path: Mapped[str] = mapped_column(String)
    relative_path_folded: Mapped[str] = mapped_column(String)
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    file_mtime: Mapped[datetime] = mapped_column(UTCDateTime)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)
    status: Mapped[str] = mapped_column(String)
    captured_at_local: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    captured_at_offset_minutes: Mapped[int | None] = mapped_column(Integer)
    captured_at_utc: Mapped[datetime | None] = mapped_column(UTCDateTime)
    captured_at_source: Mapped[str | None] = mapped_column(String)
