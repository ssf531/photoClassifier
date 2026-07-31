import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from core.infrastructure.db.base import HasId, UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration


class XmpExportRecord(HasId):
    """One row per completed XMP sidecar export (TASK-083, SDD §4.10) --
    append-only history, not a 1:1 photo state, so re-exporting a photo
    later adds a new row rather than overwriting this one.
    """

    __tablename__ = "xmp_export_record"
    __table_args__ = (Index("ix_xmp_export_record_photo_id", "photo_id"),)

    photo_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("photo.id"))
    sidecar_path: Mapped[str] = mapped_column(String)
    exported_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)
