import shutil
import uuid
from collections.abc import Sequence
from pathlib import Path

from core.domain.copy_export import CopyResultItem
from core.infrastructure.change_detection import compute_content_hash
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository


class PhotoNotFoundError(Exception):
    pass


class SourceFileMissingError(Exception):
    pass


class CopyVerificationError(Exception):
    pass


def _unique_destination(dest_dir: Path, filename: str) -> Path:
    """Never overwrites an existing file at the destination (SDD's v1
    additive-only rule): a name collision gets ` (1)`, ` (2)`, etc.,
    matching how every desktop file manager resolves a copy conflict.
    """
    candidate = dest_dir / filename
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    counter = 1
    while True:
        candidate = dest_dir / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


class CopyExportManager:
    """The one v1 bulk file-writing operation (TASK-0D): copies photos to a
    user-chosen destination folder. Additive only -- the source is only
    ever opened for reading, never modified or removed, and each copy is
    verified by content hash before being reported as a success.
    """

    def __init__(
        self, photo_repo: PhotoRepository, library_root_repo: LibraryRootRepository
    ) -> None:
        self._photos = photo_repo
        self._library_roots = library_root_repo

    async def copy_to_folder(
        self, photo_ids: Sequence[uuid.UUID], destination_folder: str
    ) -> list[CopyResultItem]:
        dest_dir = Path(destination_folder)
        items = []
        for photo_id in photo_ids:
            try:
                dest_path = await self._copy_one(photo_id, dest_dir)
                items.append(
                    CopyResultItem(photo_id=photo_id, success=True, destination_path=str(dest_path))
                )
            except (
                PhotoNotFoundError,
                SourceFileMissingError,
                CopyVerificationError,
                OSError,
            ) as exc:
                items.append(CopyResultItem(photo_id=photo_id, success=False, error=str(exc)))
        return items

    async def _copy_one(self, photo_id: uuid.UUID, dest_dir: Path) -> Path:
        photo = await self._photos.get(photo_id)
        if photo is None:
            raise PhotoNotFoundError(f"photo {photo_id} not found")
        root = await self._library_roots.get(photo.library_root_id)
        if root is None:
            raise PhotoNotFoundError(f"library root for photo {photo_id} not found")
        source_path = Path(root.path) / photo.relative_path
        if not source_path.is_file():
            raise SourceFileMissingError(f"source file for photo {photo_id} not found on disk")

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = _unique_destination(dest_dir, source_path.name)

        source_hash = compute_content_hash(source_path)
        shutil.copy2(source_path, dest_path)
        copied_hash = compute_content_hash(dest_path)
        if copied_hash != source_hash:
            dest_path.unlink(missing_ok=True)
            raise CopyVerificationError(
                f"copied file for photo {photo_id} failed content-hash verification"
            )
        return dest_path
