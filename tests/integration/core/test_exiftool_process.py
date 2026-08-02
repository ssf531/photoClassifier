from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from core.infrastructure.exiftool_process import ExifToolProcess, ExifToolWriteError, find_exiftool

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


async def test_version_returns_a_plain_version_string(exiftool: ExifToolProcess) -> None:
    version = await exiftool.version()

    assert version
    assert version[0].isdigit()


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


async def test_write_tags_creates_a_new_sidecar_from_scratch(
    tmp_path: Path, exiftool: ExifToolProcess
) -> None:
    sidecar = tmp_path / "photo.xmp"
    assert not sidecar.is_file()

    await exiftool.write_tags(
        sidecar, {"Description": "a caption", "Rating": 4, "Subject": ["dog", "beach"]}
    )

    assert sidecar.is_file()
    result = await exiftool.read_metadata(sidecar)
    assert result["Description"] == "a caption"
    assert result["Rating"] == 4
    assert set(result["Subject"]) == {"dog", "beach"}


async def test_write_tags_replaces_list_values_on_re_export_instead_of_accumulating(
    tmp_path: Path, exiftool: ExifToolProcess
) -> None:
    sidecar = tmp_path / "photo.xmp"
    await exiftool.write_tags(sidecar, {"Subject": ["dog", "beach"]})

    await exiftool.write_tags(sidecar, {"Subject": ["cat", "mountain"]})

    result = await exiftool.read_metadata(sidecar)
    assert set(result["Subject"]) == {"cat", "mountain"}


async def test_write_tags_sets_a_new_list_tag_on_a_sidecar_that_already_has_a_different_one(
    tmp_path: Path, exiftool: ExifToolProcess
) -> None:
    """Regression test (found via TASK-084 live testing): the sidecar
    already exists (created by an earlier `write_tags()` call for a
    different list tag), but this is the FIRST time `Subject` specifically
    is being set on it. `write_tags()`'s clear round for `Subject` then has
    nothing to clear -- ExifTool reports that round "unchanged", which must
    not abort the export before the real set round runs.
    """
    sidecar = tmp_path / "photo.xmp"
    await exiftool.write_tags(sidecar, {"HierarchicalSubject": ["AI Tags|dog"]})

    await exiftool.write_tags(sidecar, {"Subject": ["dog", "beach"]})

    result = await exiftool.read_metadata(sidecar)
    assert set(result["Subject"]) == {"dog", "beach"}
    assert result["HierarchicalSubject"] == "AI Tags|dog"


async def test_write_tags_never_touches_a_different_path(
    tmp_path: Path, exiftool: ExifToolProcess
) -> None:
    original = tmp_path / "photo.jpg"
    original.write_bytes(b"original bytes, untouched")
    sidecar = tmp_path / "photo.xmp"

    await exiftool.write_tags(sidecar, {"Description": "a caption"})

    assert original.read_bytes() == b"original bytes, untouched"


async def test_write_tags_raises_on_failure(tmp_path: Path, exiftool: ExifToolProcess) -> None:
    missing_dir_sidecar = tmp_path / "does-not-exist" / "photo.xmp"

    with pytest.raises(ExifToolWriteError):
        await exiftool.write_tags(missing_dir_sidecar, {"Description": "a caption"})
