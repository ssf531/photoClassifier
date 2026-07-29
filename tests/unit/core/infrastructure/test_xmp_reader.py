from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.domain.metadata import CapturedAt, NormalizedMetadata
from core.infrastructure.exiftool_process import ExifToolProcess, find_exiftool
from core.infrastructure.metadata_normalize import normalize_metadata
from core.infrastructure.xmp_reader import (
    extract_user_fields,
    read_sidecar,
    reconcile_captured_at,
    sidecar_path_for,
)

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "metadata"
FALLBACK_MTIME = datetime(2020, 1, 1, tzinfo=timezone.utc)  # noqa: UP017

pytestmark = pytest.mark.skipif(find_exiftool() is None, reason="exiftool not installed")


def _mtime_metadata() -> NormalizedMetadata:
    return NormalizedMetadata(
        camera_make=None,
        camera_model=None,
        lens=None,
        focal_length=None,
        aperture=None,
        shutter_speed=None,
        iso=None,
        gps_lat=None,
        gps_lon=None,
        width=None,
        height=None,
        orientation=None,
        captured_at=CapturedAt(local=FALLBACK_MTIME, offset_minutes=None, utc=None, source="mtime"),
        raw_exif={},
    )


def _exif_metadata() -> NormalizedMetadata:
    exif_local = datetime(2024, 6, 15, 14, 30, 0)
    return NormalizedMetadata(
        camera_make="Canon",
        camera_model="Canon EOS R5",
        lens=None,
        focal_length=None,
        aperture=None,
        shutter_speed=None,
        iso=None,
        gps_lat=None,
        gps_lon=None,
        width=None,
        height=None,
        orientation=None,
        captured_at=CapturedAt(local=exif_local, offset_minutes=None, utc=None, source="exif"),
        raw_exif={},
    )


def test_sidecar_path_for_swaps_extension_to_xmp() -> None:
    assert sidecar_path_for(Path("/lib/photo.jpg")) == Path("/lib/photo.xmp")
    assert sidecar_path_for(Path("/lib/photo.CR2")) == Path("/lib/photo.xmp")


async def test_read_sidecar_returns_none_when_no_sidecar_exists(tmp_path: Path) -> None:
    exiftool_path = find_exiftool()
    assert exiftool_path is not None
    process = ExifToolProcess(exiftool_path)
    try:
        result = await read_sidecar(process, tmp_path / "no_sidecar_here.jpg")
        assert result is None
    finally:
        await process.stop()


async def test_read_sidecar_reads_existing_sidecar() -> None:
    exiftool_path = find_exiftool()
    assert exiftool_path is not None
    process = ExifToolProcess(exiftool_path)
    try:
        result = await read_sidecar(process, FIXTURES_DIR / "canon.jpg")
        assert result is not None
        assert result["Rating"] == 5
    finally:
        await process.stop()


def test_extract_user_fields_reads_rating_caption_and_keywords() -> None:
    sidecar_raw = {
        "Rating": 5,
        "Description": "A day at the beach",
        "Subject": ["vacation", "family"],
    }

    fields = extract_user_fields(sidecar_raw)

    assert fields.rating == 5
    assert fields.caption == "A day at the beach"
    assert fields.keywords == ["vacation", "family"]


def test_extract_user_fields_handles_missing_sidecar() -> None:
    fields = extract_user_fields(None)

    assert fields.rating is None
    assert fields.caption is None
    assert fields.keywords == []


def test_extract_user_fields_handles_sidecar_with_no_user_fields() -> None:
    fields = extract_user_fields({"SourceFile": "x.xmp"})

    assert fields.rating is None
    assert fields.caption is None
    assert fields.keywords == []


async def test_end_to_end_embedded_wins_captured_at_sidecar_wins_rating() -> None:
    """The Suggested Test scenario: photo + sidecar with a pre-set rating."""
    exiftool_path = find_exiftool()
    assert exiftool_path is not None
    process = ExifToolProcess(exiftool_path)
    try:
        embedded_raw = await process.read_metadata(FIXTURES_DIR / "canon.jpg")
        sidecar_raw = await read_sidecar(process, FIXTURES_DIR / "canon.jpg")
    finally:
        await process.stop()

    metadata = normalize_metadata(embedded_raw, FALLBACK_MTIME)
    reconciled = reconcile_captured_at(metadata, sidecar_raw)
    user_fields = extract_user_fields(sidecar_raw)

    # embedded wins: canon.jpg has its own DateTimeOriginal, untouched by the sidecar
    assert reconciled.captured_at.source == "exif"
    assert reconciled.captured_at.local == datetime(2024, 6, 15, 14, 30, 0)
    # sidecar wins: rating has no embedded competitor, sidecar is authoritative
    assert user_fields.rating == 5
    assert user_fields.caption == "A day at the beach"
    assert set(user_fields.keywords) == {"vacation", "family"}


def test_reconcile_keeps_embedded_captured_at_even_with_sidecar_date() -> None:
    metadata = _exif_metadata()
    sidecar_raw = {"DateTimeOriginal": "2099:01:01 00:00:00"}

    reconciled = reconcile_captured_at(metadata, sidecar_raw)

    assert reconciled is metadata


def test_reconcile_fills_gap_from_sidecar_when_embedded_has_no_date() -> None:
    metadata = _mtime_metadata()
    sidecar_raw = {"DateTimeOriginal": "2024:06:15 14:30:00+09:00"}

    reconciled = reconcile_captured_at(metadata, sidecar_raw)

    assert reconciled.captured_at.source == "xmp"
    assert reconciled.captured_at.local == datetime(2024, 6, 15, 14, 30, 0)
    assert reconciled.captured_at.offset_minutes == 540
    assert reconciled.captured_at.utc == datetime(2024, 6, 15, 5, 30, 0)


def test_reconcile_keeps_mtime_when_sidecar_has_no_date_either() -> None:
    metadata = _mtime_metadata()

    reconciled = reconcile_captured_at(metadata, {"Rating": 5})

    assert reconciled is metadata


def test_reconcile_keeps_mtime_when_no_sidecar_at_all() -> None:
    metadata = _mtime_metadata()

    reconciled = reconcile_captured_at(metadata, None)

    assert reconciled is metadata
