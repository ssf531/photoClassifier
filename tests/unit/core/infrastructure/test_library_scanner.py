import os
from pathlib import Path

import pytest

from core.infrastructure.library_scanner import _to_long_path, walk


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def _relative_names(paths: object, root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in paths}  # type: ignore[union-attr]


def test_walk_discovers_supported_formats_and_skips_unsupported(tmp_path: Path) -> None:
    _touch(tmp_path / "a.jpg")
    _touch(tmp_path / "b.CR2")
    _touch(tmp_path / "c.heic")
    _touch(tmp_path / "notes.txt")
    _touch(tmp_path / "sub" / "d.png")

    found = _relative_names(walk(tmp_path), tmp_path)

    assert found == {"a.jpg", "b.CR2", "sub/d.png", "c.heic"}


def test_walk_respects_exclude_globs(tmp_path: Path) -> None:
    _touch(tmp_path / "keep.jpg")
    _touch(tmp_path / ".thumbnails" / "cache.jpg")

    found = _relative_names(walk(tmp_path, exclude_globs=["*.thumbnails/*"]), tmp_path)

    assert found == {"keep.jpg"}


def test_walk_respects_include_globs(tmp_path: Path) -> None:
    _touch(tmp_path / "2024" / "a.jpg")
    _touch(tmp_path / "2023" / "b.jpg")

    found = _relative_names(walk(tmp_path, include_globs=["2024/*"]), tmp_path)

    assert found == {"2024/a.jpg"}


def test_walk_does_not_follow_symlinked_directories_by_default(tmp_path: Path) -> None:
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    _touch(real_dir / "a.jpg")
    link_dir = tmp_path / "link"
    try:
        link_dir.symlink_to(real_dir, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation requires elevated privileges on this system")

    found = _relative_names(walk(tmp_path), tmp_path)

    assert found == {"real/a.jpg"}


def test_walk_follows_symlinks_when_opted_in(tmp_path: Path) -> None:
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    _touch(real_dir / "a.jpg")
    link_dir = tmp_path / "link"
    try:
        link_dir.symlink_to(real_dir, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation requires elevated privileges on this system")

    found = _relative_names(walk(tmp_path, follow_symlinks=True), tmp_path)

    assert found == {"real/a.jpg", "link/a.jpg"}


def test_walk_handles_paths_beyond_max_path(tmp_path: Path) -> None:
    deep = tmp_path
    for i in range(20):
        deep = deep / f"segment_{i:03d}_padding_to_make_this_long"
    deep.mkdir(parents=True)
    (deep / "deep.jpg").write_bytes(b"")
    assert len(str(deep)) > 260

    found = list(walk(tmp_path))

    assert len(found) == 1
    assert found[0].name == "deep.jpg"


def test_to_long_path_prefixes_on_windows(tmp_path: Path) -> None:
    result = _to_long_path(tmp_path)

    if os.name == "nt":
        assert str(result) == "\\\\?\\" + str(tmp_path)
    else:
        assert result == tmp_path


def test_to_long_path_is_idempotent(tmp_path: Path) -> None:
    once = _to_long_path(tmp_path)
    twice = _to_long_path(once)

    assert str(once) == str(twice)
