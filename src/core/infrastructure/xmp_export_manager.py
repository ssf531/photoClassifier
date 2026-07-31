import uuid
from collections.abc import Sequence
from pathlib import Path

from core.domain.export import ExportResultItem
from core.domain.plugins import Capability
from core.infrastructure.ai_result_repository import AiResultRepository
from core.infrastructure.collection_repository import UserDataRepository
from core.infrastructure.db.export_models import XmpExportRecord
from core.infrastructure.exiftool_process import ExifToolProcess, ExifToolWriteError
from core.infrastructure.export_repository import XmpExportRecordRepository
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.xmp_reader import sidecar_path_for


class PhotoNotFoundError(Exception):
    pass


class NothingToExportError(Exception):
    """No AI result or rating exists yet for this photo -- there is
    genuinely nothing to write, distinct from a real export failure.
    """


class XmpExportManager:
    """`export_xmp()` (TASK-083, SDD §4.10): writes the current caption,
    tags, and rating to an XMP sidecar next to the photo, via ExifTool
    (TASK-023) -- never the original file itself, since only the sidecar
    path is ever passed to a write command. Additive only, matching every
    other v1 curation action: nothing is deleted or modified in place.
    """

    def __init__(
        self,
        exiftool: ExifToolProcess,
        photo_repo: PhotoRepository,
        library_root_repo: LibraryRootRepository,
        ai_result_repo: AiResultRepository,
        user_data_repo: UserDataRepository,
        export_record_repo: XmpExportRecordRepository,
    ) -> None:
        self._exiftool = exiftool
        self._photos = photo_repo
        self._library_roots = library_root_repo
        self._ai_results = ai_result_repo
        self._user_data = user_data_repo
        self._export_records = export_record_repo

    async def export_xmp(self, photo_ids: Sequence[uuid.UUID]) -> list[ExportResultItem]:
        items = []
        for photo_id in photo_ids:
            try:
                sidecar_path = await self._export_one(photo_id)
                items.append(ExportResultItem(photo_id=photo_id, success=True))
                await self._export_records.create(
                    XmpExportRecord(photo_id=photo_id, sidecar_path=str(sidecar_path))
                )
            except (PhotoNotFoundError, NothingToExportError, ExifToolWriteError) as exc:
                items.append(ExportResultItem(photo_id=photo_id, success=False, error=str(exc)))
        return items

    async def _export_one(self, photo_id: uuid.UUID) -> Path:
        photo = await self._photos.get(photo_id)
        if photo is None:
            raise PhotoNotFoundError(f"photo {photo_id} not found")
        root = await self._library_roots.get(photo.library_root_id)
        if root is None:
            raise PhotoNotFoundError(f"library root for photo {photo_id} not found")
        photo_path = Path(root.path) / photo.relative_path
        sidecar_path = sidecar_path_for(photo_path)

        tags: dict[str, str | int | list[str]] = {}
        for result in await self._ai_results.list_current_by_photo(photo_id):
            if result.capability == Capability.CAPTION.value:
                caption = result.payload.get("caption")
                if caption:
                    tags["Description"] = caption
            elif result.capability == Capability.TAG.value:
                labels = [tag["label"] for tag in result.payload.get("tags", [])]
                if labels:
                    tags["Subject"] = labels

        user_data = await self._user_data.get_by_photo_id(photo_id)
        if user_data is not None and user_data.rating is not None:
            tags["Rating"] = user_data.rating

        if not tags:
            raise NothingToExportError(f"photo {photo_id} has no AI result or rating to export")

        await self._exiftool.write_tags(sidecar_path, tags)
        return sidecar_path
