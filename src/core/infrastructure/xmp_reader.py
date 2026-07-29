import dataclasses
from datetime import timedelta
from pathlib import Path
from typing import Any

from core.domain.metadata import CapturedAt, NormalizedMetadata
from core.infrastructure.exiftool_process import ExifToolProcess
from core.infrastructure.metadata_normalize import first_str, parse_datetime_with_optional_offset


def sidecar_path_for(photo_path: Path) -> Path:
    return photo_path.with_suffix(".xmp")


@dataclasses.dataclass(frozen=True)
class XmpUserFields:
    """User-authored fields a pre-existing XMP sidecar may carry.

    Sidecar wins for these (SDD §4.2) since there is no embedded-EXIF
    competitor for them. Persisting these onto `user_data` is out of scope
    here: that table lands with TASK-030 (Collections, Phase 6); callers
    hold onto this result until it exists.
    """

    rating: int | None
    caption: str | None
    keywords: list[str]


async def read_sidecar(exiftool: ExifToolProcess, photo_path: Path) -> dict[str, Any] | None:
    sidecar_path = sidecar_path_for(photo_path)
    if not sidecar_path.is_file():
        return None
    return await exiftool.read_metadata(sidecar_path)


def extract_user_fields(sidecar_raw: dict[str, Any] | None) -> XmpUserFields:
    if sidecar_raw is None:
        return XmpUserFields(rating=None, caption=None, keywords=[])

    rating_value = sidecar_raw.get("Rating")
    rating = int(rating_value) if isinstance(rating_value, int | float) else None

    caption_value = sidecar_raw.get("Description")
    caption = str(caption_value) if caption_value is not None else None

    subject_value = sidecar_raw.get("Subject")
    keywords = [str(k) for k in subject_value] if isinstance(subject_value, list) else []

    return XmpUserFields(rating=rating, caption=caption, keywords=keywords)


def reconcile_captured_at(
    metadata: NormalizedMetadata, sidecar_raw: dict[str, Any] | None
) -> NormalizedMetadata:
    """Embedded EXIF wins for the capture time; XMP only fills a gap.

    Per SDD §4.2 / ADR-0011: if embedded metadata already supplied a capture
    time, the sidecar never overrides it. Only when embedded had nothing
    (captured_at.source == "mtime") does a sidecar-supplied date get used.
    """
    if metadata.captured_at.source != "mtime" or sidecar_raw is None:
        return metadata

    raw_dt = first_str(sidecar_raw, "DateTimeOriginal", "DateCreated", "CreateDate")
    local, offset_minutes = parse_datetime_with_optional_offset(raw_dt)
    if local is None:
        return metadata

    utc = local - timedelta(minutes=offset_minutes) if offset_minutes is not None else None
    return dataclasses.replace(
        metadata,
        captured_at=CapturedAt(local=local, offset_minutes=offset_minutes, utc=utc, source="xmp"),
    )
