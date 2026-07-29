from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from core.infrastructure.exiftool_process import ExifToolProcess, find_exiftool

pytestmark = pytest.mark.skipif(find_exiftool() is None, reason="exiftool not installed")


@pytest.fixture
async def exiftool() -> AsyncIterator[ExifToolProcess]:
    path = find_exiftool()
    assert path is not None
    process = ExifToolProcess(path)
    try:
        yield process
    finally:
        await process.stop()


async def test_read_metadata_returns_source_file(tmp_path: Path, exiftool: ExifToolProcess) -> None:
    image = tmp_path / "a.jpg"
    image.write_bytes(b"not a real jpeg but exiftool still reports file info")

    result = await exiftool.read_metadata(image)

    assert Path(result["SourceFile"]) == image


async def test_read_metadata_batch_returns_one_result_per_file(
    tmp_path: Path, exiftool: ExifToolProcess
) -> None:
    images = [tmp_path / f"{i}.jpg" for i in range(5)]
    for image in images:
        image.write_bytes(b"x")

    results = await exiftool.read_metadata_batch(images)

    assert len(results) == 5
    assert {Path(r["SourceFile"]) for r in results} == set(images)


async def test_only_one_process_is_ever_spawned_across_many_reads(
    tmp_path: Path, exiftool: ExifToolProcess
) -> None:
    for i in range(10):
        image = tmp_path / f"{i}.jpg"
        image.write_bytes(b"x")
        await exiftool.read_metadata(image)

    assert exiftool._process is not None
    pid = exiftool._process.pid

    for i in range(10, 20):
        image = tmp_path / f"{i}.jpg"
        image.write_bytes(b"x")
        await exiftool.read_metadata(image)

    assert exiftool._process.pid == pid


async def test_stop_terminates_the_process(tmp_path: Path, exiftool: ExifToolProcess) -> None:
    image = tmp_path / "a.jpg"
    image.write_bytes(b"x")
    await exiftool.read_metadata(image)

    process = exiftool._process
    assert process is not None

    await exiftool.stop()

    assert process.returncode is not None
    assert exiftool._process is None
