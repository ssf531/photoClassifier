import ctypes
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

import xxhash

from core.domain.library import PhotoId

_HASH_CHUNK_SIZE = 1024 * 1024
_DRIVE_REMOTE = 4


def compute_content_hash(path: Path) -> str:
    hasher = xxhash.xxh3_64()
    with path.open("rb") as f:
        while chunk := f.read(_HASH_CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.hexdigest()


def is_local_path(path: Path) -> bool:
    raw = str(path)
    if raw.startswith("\\\\"):
        return False
    if os.name != "nt":
        return True
    drive = path.drive
    if not drive:
        return True
    try:
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(f"{drive}\\")
    except OSError:
        return True
    return bool(drive_type != _DRIVE_REMOTE)


class ChangeKind(str, Enum):  # noqa: UP042 -- kept pre-StrEnum pending broader migration
    NEW = "new"
    MODIFIED = "modified"
    MOVED = "moved"
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class DiscoveredFile:
    relative_path: str
    absolute_path: Path
    size_bytes: int
    mtime: datetime


@dataclass(frozen=True)
class ExistingPhoto:
    photo_id: PhotoId
    relative_path: str
    relative_path_folded: str
    content_hash: str | None
    size_bytes: int
    file_mtime: datetime


@dataclass(frozen=True)
class Classification:
    kind: ChangeKind
    discovered: DiscoveredFile
    existing_photo_id: PhotoId | None = None
    previous_relative_path: str | None = None
    content_hash: str | None = None


def classify_changes(
    discovered: list[DiscoveredFile],
    existing: list[ExistingPhoto],
    *,
    is_local: bool,
    hash_fn: Callable[[Path], str] = compute_content_hash,
) -> list[Classification]:
    existing_by_folded_path = {row.relative_path_folded: row for row in existing}
    unresolved: list[DiscoveredFile] = []
    results: list[Classification] = []

    for file in discovered:
        folded = file.relative_path.lower()
        matched = existing_by_folded_path.pop(folded, None)
        if matched is None:
            unresolved.append(file)
            continue
        results.append(_classify_same_path(file, matched, is_local=is_local, hash_fn=hash_fn))

    remaining_by_hash: dict[str, ExistingPhoto] = {
        row.content_hash: row for row in existing_by_folded_path.values() if row.content_hash
    }
    remaining_by_signature: dict[tuple[int, datetime], ExistingPhoto] = {
        (row.size_bytes, row.file_mtime): row for row in existing_by_folded_path.values()
    }

    for file in unresolved:
        content_hash = hash_fn(file.absolute_path) if is_local else None

        if is_local and content_hash is not None:
            moved_from = remaining_by_hash.get(content_hash)
        else:
            moved_from = remaining_by_signature.get((file.size_bytes, file.mtime))

        if moved_from is not None:
            results.append(
                Classification(
                    kind=ChangeKind.MOVED,
                    discovered=file,
                    existing_photo_id=moved_from.photo_id,
                    previous_relative_path=moved_from.relative_path,
                    content_hash=content_hash,
                )
            )
            continue

        results.append(
            Classification(kind=ChangeKind.NEW, discovered=file, content_hash=content_hash)
        )

    return results


def _classify_same_path(
    file: DiscoveredFile,
    matched: ExistingPhoto,
    *,
    is_local: bool,
    hash_fn: Callable[[Path], str],
) -> Classification:
    unchanged_by_stat = file.size_bytes == matched.size_bytes and file.mtime == matched.file_mtime
    if unchanged_by_stat:
        return Classification(
            kind=ChangeKind.UNCHANGED, discovered=file, existing_photo_id=matched.photo_id
        )

    if not is_local:
        return Classification(
            kind=ChangeKind.MODIFIED, discovered=file, existing_photo_id=matched.photo_id
        )

    new_hash = hash_fn(file.absolute_path)
    if new_hash == matched.content_hash:
        return Classification(
            kind=ChangeKind.UNCHANGED,
            discovered=file,
            existing_photo_id=matched.photo_id,
            content_hash=new_hash,
        )
    return Classification(
        kind=ChangeKind.MODIFIED,
        discovered=file,
        existing_photo_id=matched.photo_id,
        content_hash=new_hash,
    )
