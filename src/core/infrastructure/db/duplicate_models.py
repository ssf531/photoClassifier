import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Float, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from core.infrastructure.db.base import HasId, UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration


class DuplicateGroup(HasId):
    __tablename__ = "duplicate_group"

    detection_method: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)


class DuplicateGroupMember(HasId):
    __tablename__ = "duplicate_group_member"
    __table_args__ = (UniqueConstraint("group_id", "photo_id"),)

    group_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("duplicate_group.id"))
    photo_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("photo.id"))
    similarity_score: Mapped[float] = mapped_column(Float)
    is_recommended_keeper: Mapped[bool] = mapped_column(Boolean, default=False)
