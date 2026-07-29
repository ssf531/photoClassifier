import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from core.infrastructure.db.base import HasId, UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration


class AiResult(HasId):
    __tablename__ = "ai_result"
    __table_args__ = (
        Index("ix_ai_result_photo_capability_current", "photo_id", "capability", "is_current"),
        Index("ix_ai_result_plugin_model_version", "plugin_id", "model_version"),
    )

    photo_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("photo.id"))
    plugin_id: Mapped[str] = mapped_column(String, ForeignKey("plugin.id"))
    capability: Mapped[str] = mapped_column(String)
    model_version: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)


class EmbeddingRef(HasId):
    __tablename__ = "embedding_ref"
    __table_args__ = (
        UniqueConstraint("photo_id", "vector_space", name="uq_embedding_ref_photo_vector_space"),
    )

    photo_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("photo.id"))
    plugin_id: Mapped[str] = mapped_column(String, ForeignKey("plugin.id"))
    model_version: Mapped[str] = mapped_column(String)
    vector_space: Mapped[str] = mapped_column(String)
    vector_key: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_utcnow)
