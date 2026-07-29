import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.infrastructure.exiftool_process import ExifToolProcess, find_exiftool
from core.infrastructure.metadata_normalize import normalize_metadata

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "metadata"
FALLBACK_MTIME = datetime(2020, 1, 1, tzinfo=timezone.utc)  # noqa: UP017

pytestmark = pytest.mark.skipif(find_exiftool() is None, reason="exiftool not installed")


async def _read_raw(filename: str) -> dict[str, object]:
    path = find_exiftool()
    assert path is not None
    process = ExifToolProcess(path)
    try:
        return await process.read_metadata(FIXTURES_DIR / filename)
    finally:
        await process.stop()


async def test_canon_fixture_normalizes_all_known_fields() -> None:
    raw = await _read_raw("canon.jpg")

    result = normalize_metadata(raw, FALLBACK_MTIME)

    assert result.camera_make == "Canon"
    assert result.camera_model == "Canon EOS R5"
    assert result.lens == "RF24-105mm F4 L IS USM"
    assert result.focal_length == 50
    assert result.aperture == 4
    assert result.shutter_speed == pytest.approx(0.005)
    assert result.iso == 400
    assert result.width == 64
    assert result.height == 48
    assert result.orientation == 1
    assert result.gps_lat == pytest.approx(35.6586, abs=1e-3)
    assert result.gps_lon == pytest.approx(139.7454, abs=1e-3)
    assert result.captured_at.source == "exif"
    assert result.captured_at.local == datetime(2024, 6, 15, 14, 30, 0)
    assert result.captured_at.offset_minutes is None
    assert result.captured_at.utc is None


async def test_nikon_fixture_computes_utc_from_known_offset() -> None:
    raw = await _read_raw("nikon.jpg")

    result = normalize_metadata(raw, FALLBACK_MTIME)

    assert result.camera_make == "NIKON CORPORATION"
    assert result.lens == "NIKKOR Z 24-70mm f/2.8 S"
    assert result.orientation == 6
    assert result.captured_at.source == "exif"
    assert result.captured_at.local == datetime(2024, 3, 10, 9, 15, 30)
    assert result.captured_at.offset_minutes == 540
    assert result.captured_at.utc == datetime(2024, 3, 10, 0, 15, 30)


async def test_sony_fixture_falls_back_to_mtime_when_no_capture_time() -> None:
    raw = await _read_raw("sony.jpg")

    result = normalize_metadata(raw, FALLBACK_MTIME)

    assert result.camera_make == "SONY"
    assert result.lens == "FE 85mm F1.4 GM"
    assert result.captured_at.source == "mtime"
    assert result.captured_at.local == FALLBACK_MTIME
    assert result.captured_at.offset_minutes is None
    assert result.captured_at.utc is None


@pytest.mark.parametrize("filename", ["canon.jpg", "nikon.jpg", "sony.jpg"])
async def test_raw_exif_blob_preserves_every_reported_field(filename: str) -> None:
    raw = await _read_raw(filename)

    result = normalize_metadata(raw, FALLBACK_MTIME)

    assert result.raw_exif == raw
    # every field ExifTool reported must round-trip through JSON untouched
    assert json.loads(json.dumps(result.raw_exif)) == raw
    for key, value in raw.items():
        assert key in result.raw_exif
        assert result.raw_exif[key] == value


def test_missing_offset_produces_no_utc() -> None:
    raw = {"DateTimeOriginal": "2024:01:01 10:00:00"}

    result = normalize_metadata(raw, FALLBACK_MTIME)

    assert result.captured_at.local == datetime(2024, 1, 1, 10, 0, 0)
    assert result.captured_at.offset_minutes is None
    assert result.captured_at.utc is None


def test_negative_offset_computes_utc_correctly() -> None:
    raw = {
        "DateTimeOriginal": "2024:01:01 10:00:00",
        "OffsetTimeOriginal": "-05:00",
    }

    result = normalize_metadata(raw, FALLBACK_MTIME)

    assert result.captured_at.offset_minutes == -300
    assert result.captured_at.utc == datetime(2024, 1, 1, 15, 0, 0)


def test_no_datetime_at_all_falls_back_to_mtime() -> None:
    result = normalize_metadata({}, FALLBACK_MTIME)

    assert result.captured_at.source == "mtime"
    assert result.captured_at.local == FALLBACK_MTIME


def test_unparseable_datetime_falls_back_to_mtime() -> None:
    raw = {"DateTimeOriginal": "not-a-date"}

    result = normalize_metadata(raw, FALLBACK_MTIME)

    assert result.captured_at.source == "mtime"
    assert result.captured_at.local == FALLBACK_MTIME
