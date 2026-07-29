import re
from datetime import datetime, timedelta
from typing import Any

from core.domain.metadata import CapturedAt, NormalizedMetadata

_EXIF_DATETIME_FORMAT = "%Y:%m:%d %H:%M:%S"
_OFFSET_PATTERN = re.compile(r"^([+-])(\d{2}):(\d{2})$")
_DATETIME_WITH_OPTIONAL_OFFSET = re.compile(
    r"^(?P<dt>\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2})(?P<offset>[+-]\d{2}:\d{2})?$"
)


def first_str(raw: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = raw.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _first_number(raw: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str) and value.strip():
            try:
                return float(value)
            except ValueError:
                continue
    return None


def _first_int(raw: dict[str, Any], *keys: str) -> int | None:
    value = _first_number(raw, *keys)
    return int(value) if value is not None else None


def _parse_exif_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, _EXIF_DATETIME_FORMAT)
    except ValueError:
        return None


def _parse_offset_minutes(value: str | None) -> int | None:
    if not value:
        return None
    match = _OFFSET_PATTERN.match(value.strip())
    if not match:
        return None
    sign, hours, minutes = match.groups()
    total = int(hours) * 60 + int(minutes)
    return -total if sign == "-" else total


def parse_datetime_with_optional_offset(value: str | None) -> tuple[datetime | None, int | None]:
    """Parse an ExifTool datetime string that may carry an inline offset.

    ExifTool normalizes embedded EXIF and XMP dates to the same "YYYY:MM:DD
    HH:MM:SS" base, but an offset arrives differently per source: EXIF as a
    separate tag (OffsetTimeOriginal), XMP inline on the datetime itself
    (e.g. "2024:06:15 14:30:00+09:00"). This handles the inline form; callers
    fall back to a separate offset tag when this returns None for the offset.
    """
    if not value:
        return None, None
    match = _DATETIME_WITH_OPTIONAL_OFFSET.match(value.strip())
    if not match:
        return _parse_exif_datetime(value), None
    local = _parse_exif_datetime(match.group("dt"))
    offset = _parse_offset_minutes(match.group("offset")) if match.group("offset") else None
    return local, offset


def _compute_captured_at(raw: dict[str, Any], fallback_mtime: datetime) -> CapturedAt:
    raw_dt = first_str(raw, "DateTimeOriginal", "CreateDate")
    local, inline_offset = parse_datetime_with_optional_offset(raw_dt)
    if local is not None:
        offset_minutes = inline_offset
        if offset_minutes is None:
            offset_minutes = _parse_offset_minutes(
                first_str(raw, "OffsetTimeOriginal", "OffsetTime")
            )
        utc = local - timedelta(minutes=offset_minutes) if offset_minutes is not None else None
        return CapturedAt(local=local, offset_minutes=offset_minutes, utc=utc, source="exif")

    return CapturedAt(local=fallback_mtime, offset_minutes=None, utc=None, source="mtime")


def normalize_metadata(raw: dict[str, Any], fallback_mtime: datetime) -> NormalizedMetadata:
    return NormalizedMetadata(
        camera_make=first_str(raw, "Make"),
        camera_model=first_str(raw, "Model"),
        lens=first_str(raw, "LensModel", "LensID", "Lens"),
        focal_length=_first_number(raw, "FocalLength"),
        aperture=_first_number(raw, "FNumber", "Aperture"),
        shutter_speed=_first_number(raw, "ExposureTime", "ShutterSpeed"),
        iso=_first_int(raw, "ISO"),
        gps_lat=_first_number(raw, "GPSLatitude"),
        gps_lon=_first_number(raw, "GPSLongitude"),
        width=_first_int(raw, "ImageWidth", "ExifImageWidth"),
        height=_first_int(raw, "ImageHeight", "ExifImageHeight"),
        orientation=_first_int(raw, "Orientation"),
        captured_at=_compute_captured_at(raw, fallback_mtime),
        raw_exif=raw,
    )
