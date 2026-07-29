import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.infrastructure.db.base import Base, HasId, UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration


class UserData(Base):
    __tablename__ = "user_data"

    photo_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("photo.id"), primary_key=True)
    rating: Mapped[int | None] = mapped_column(Integer)
    favourite: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow, onupdate=_utcnow)


class Collection(HasId):
    __tablename__ = "collection"

    name: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)  # "virtual" | "smart"
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)


class SmartCollectionRule(Base):
    __tablename__ = "smart_collection_rule"

    collection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("collection.id"), primary_key=True
    )
    search_query: Mapped[dict[str, Any]] = mapped_column(JSON)


class CollectionItem(HasId):
    __tablename__ = "collection_item"
    __table_args__ = (UniqueConstraint("collection_id", "photo_id"),)

    collection_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("collection.id"))
    photo_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("photo.id"))
    added_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)
