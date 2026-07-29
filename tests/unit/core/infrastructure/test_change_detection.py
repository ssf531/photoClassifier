import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.infrastructure.change_detection import (
    ChangeKind,
    DiscoveredFile,
    ExistingPhoto,
    classify_changes,
    compute_content_hash,
    is_local_path,
)

_T1 = datetime(2024, 1, 1, tzinfo=timezone.utc)  # noqa: UP017
_T2 = datetime(2024, 6, 1, tzinfo=timezone.utc)  # noqa: UP017


def _fake_hash(path: Path) -> str:
    return f"hash:{path.name}"


def _discovered(relative_path: str, size: int = 100, mtime: datetime = _T1) -> DiscoveredFile:
    return DiscoveredFile(
        relative_path=relative_path,
        absolute_path=Path(f"/lib/{relative_path}"),
        size_bytes=size,
        mtime=mtime,
    )


def _existing(
    relative_path: str,
    *,
    content_hash: str | None,
    size: int = 100,
    mtime: datetime = _T1,
) -> ExistingPhoto:
    return ExistingPhoto(
        photo_id=uuid.uuid4(),
        relative_path=relative_path,
        relative_path_folded=relative_path.lower(),
        content_hash=content_hash,
        size_bytes=size,
        file_mtime=mtime,
    )


def test_unchanged_file_same_path_same_stat() -> None:
    existing = _existing("a.jpg", content_hash="hash:a.jpg")
    discovered = _discovered("a.jpg")

    (result,) = classify_changes([discovered], [existing], is_local=True, hash_fn=_fake_hash)

    assert result.kind == ChangeKind.UNCHANGED
    assert result.existing_photo_id == existing.photo_id


def test_content_edit_classified_as_modified() -> None:
    existing = _existing("a.jpg", content_hash="hash:old-content", mtime=_T1)
    discovered = _discovered("a.jpg", mtime=_T2)

    (result,) = classify_changes([discovered], [existing], is_local=True, hash_fn=_fake_hash)

    assert result.kind == ChangeKind.MODIFIED
    assert result.existing_photo_id == existing.photo_id
    assert result.content_hash == "hash:a.jpg"


def test_rename_between_scans_classified_as_moved() -> None:
    existing = _existing("old_name.jpg", content_hash="hash:shared.jpg")
    discovered = _discovered("shared.jpg")

    (result,) = classify_changes([discovered], [existing], is_local=True, hash_fn=_fake_hash)

    assert result.kind == ChangeKind.MOVED
    assert result.existing_photo_id == existing.photo_id
    assert result.previous_relative_path == "old_name.jpg"


def test_genuinely_new_file_has_no_existing_match() -> None:
    discovered = _discovered("brand_new.jpg")

    (result,) = classify_changes([discovered], [], is_local=True, hash_fn=_fake_hash)

    assert result.kind == ChangeKind.NEW
    assert result.existing_photo_id is None
    assert result.content_hash == "hash:brand_new.jpg"


def test_non_local_root_uses_size_and_mtime_only_no_hash_called() -> None:
    existing = _existing("a.jpg", content_hash=None, size=100, mtime=_T1)
    discovered = _discovered("a.jpg", size=100, mtime=_T2)

    def _hash_fn_should_not_be_called(path: Path) -> str:
        raise AssertionError("hash_fn must not be called for non-local roots")

    (result,) = classify_changes(
        [discovered], [existing], is_local=False, hash_fn=_hash_fn_should_not_be_called
    )

    assert result.kind == ChangeKind.MODIFIED
    assert result.content_hash is None


def test_non_local_root_rename_detected_via_size_and_mtime() -> None:
    existing = _existing("old_name.jpg", content_hash=None, size=200, mtime=_T2)
    discovered = _discovered("new_name.jpg", size=200, mtime=_T2)

    def _hash_fn_should_not_be_called(path: Path) -> str:
        raise AssertionError("hash_fn must not be called for non-local roots")

    (result,) = classify_changes(
        [discovered], [existing], is_local=False, hash_fn=_hash_fn_should_not_be_called
    )

    assert result.kind == ChangeKind.MOVED
    assert result.previous_relative_path == "old_name.jpg"


def test_case_only_rename_matches_via_folded_path() -> None:
    existing = _existing("Vacation/IMG_0001.JPG", content_hash="hash:IMG_0001.JPG")
    discovered = _discovered("vacation/img_0001.jpg")

    (result,) = classify_changes([discovered], [existing], is_local=True, hash_fn=_fake_hash)

    assert result.kind == ChangeKind.UNCHANGED


def test_compute_content_hash_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "a.bin"
    path.write_bytes(b"hello world" * 1000)

    assert compute_content_hash(path) == compute_content_hash(path)


def test_compute_content_hash_differs_for_different_content(tmp_path: Path) -> None:
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"content a")
    b.write_bytes(b"content b")

    assert compute_content_hash(a) != compute_content_hash(b)


def test_is_local_path_rejects_unc_paths() -> None:
    assert is_local_path(Path("\\\\server\\share\\photos")) is False


def test_is_local_path_accepts_ordinary_path(tmp_path: Path) -> None:
    assert is_local_path(tmp_path) is True
