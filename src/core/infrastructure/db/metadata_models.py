import uuid
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from core.infrastructure.db.base import Base


class Metadata(Base):
    __tablename__ = "metadata"

    photo_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("photo.id"), primary_key=True)
    camera_make: Mapped[str | None] = mapped_column(String)
    camera_model: Mapped[str | None] = mapped_column(String)
    lens: Mapped[str | None] = mapped_column(String)
    focal_length: Mapped[float | None] = mapped_column(Float)
    aperture: Mapped[float | None] = mapped_column(Float)
    shutter_speed: Mapped[float | None] = mapped_column(Float)
    iso: Mapped[int | None] = mapped_column(Integer)
    gps_lat: Mapped[float | None] = mapped_column(Float)
    gps_lon: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    orientation: Mapped[int | None] = mapped_column(Integer)
    raw_exif_blob: Mapped[dict[str, Any]] = mapped_column(JSON)
