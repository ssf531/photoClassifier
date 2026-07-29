from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class CapturedAt:
    local: datetime | None
    offset_minutes: int | None
    utc: datetime | None
    source: str  # "exif" | "xmp" | "gps" | "mtime"


@dataclass(frozen=True)
class NormalizedMetadata:
    camera_make: str | None
    camera_model: str | None
    lens: str | None
    focal_length: float | None
    aperture: float | None
    shutter_speed: float | None
    iso: int | None
    gps_lat: float | None
    gps_lon: float | None
    width: int | None
    height: int | None
    orientation: int | None
    captured_at: CapturedAt
    raw_exif: dict[str, Any]
