import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path

from core.domain.library import FileStatus
from core.domain.plugins import Capability
from core.domain.scheduler import JobSpec, TaskScheduler
from core.infrastructure.analysis_job import ANALYSIS_JOB_TYPE
from core.infrastructure.change_detection import (
    ChangeKind,
    Classification,
    DiscoveredFile,
    ExistingPhoto,
    classify_changes,
    is_local_path,
)
from core.infrastructure.db.library_models import Photo
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.library_scanner import walk
from core.infrastructure.scheduler import JobContext

SCAN_JOB_TYPE = "scan"
_PAGE_SIZE = 500


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration


async def _fetch_all_existing_photos(
    photo_repo: PhotoRepository, library_root_id: uuid.UUID
) -> list[Photo]:
    rows: list[Photo] = []
    offset = 0
    while True:
        page = await photo_repo.list_by_library_root(
            library_root_id, limit=_PAGE_SIZE, offset=offset
        )
        rows.extend(page)
        if len(page) < _PAGE_SIZE:
            return rows
        offset += _PAGE_SIZE


def _discover_files(root_path: Path) -> list[DiscoveredFile]:
    discovered: list[DiscoveredFile] = []
    for path in walk(root_path):
        stat = path.stat()
        relative_path = path.relative_to(root_path).as_posix()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)  # noqa: UP017
        discovered.append(
            DiscoveredFile(
                relative_path=relative_path,
                absolute_path=path,
                size_bytes=stat.st_size,
                mtime=mtime,
            )
        )
    return discovered


async def _apply_classification(
    photo_repo: PhotoRepository, library_root_id: uuid.UUID, classification: Classification
) -> uuid.UUID:
    if classification.kind == ChangeKind.NEW:
        created = await photo_repo.create(
            Photo(
                library_root_id=library_root_id,
                relative_path=classification.discovered.relative_path,
                relative_path_folded=classification.discovered.relative_path.lower(),
                content_hash=classification.content_hash,
                size_bytes=classification.discovered.size_bytes,
                file_mtime=classification.discovered.mtime,
                status=FileStatus.ACTIVE.value,
            )
        )
        return created.id

    existing_photo_id = classification.existing_photo_id
    if existing_photo_id is None:
        raise ValueError(f"classification {classification.kind} is missing existing_photo_id")

    photo = await photo_repo.get(existing_photo_id)
    if photo is None:
        raise ValueError(f"photo {existing_photo_id} referenced by scan no longer exists")

    photo.size_bytes = classification.discovered.size_bytes
    photo.file_mtime = classification.discovered.mtime
    photo.last_seen_at = _utcnow()
    photo.status = FileStatus.ACTIVE.value
    if classification.kind == ChangeKind.MOVED:
        photo.relative_path = classification.discovered.relative_path
        photo.relative_path_folded = classification.discovered.relative_path.lower()
    if classification.content_hash is not None:
        photo.content_hash = classification.content_hash

    await photo_repo.update(photo)
    return photo.id


async def _reconcile_absent_photos(
    photo_repo: PhotoRepository,
    existing_rows: list[Photo],
    matched_photo_ids: set[uuid.UUID],
    grace_period_days: int,
) -> None:
    now = _utcnow()
    for row in existing_rows:
        if row.id in matched_photo_ids or row.status == FileStatus.DELETED.value:
            continue
        age_days = (now - row.last_seen_at).days
        new_status = (
            FileStatus.DELETED.value if age_days >= grace_period_days else FileStatus.MISSING.value
        )
        if row.status != new_status:
            row.status = new_status
            await photo_repo.update(row)


def create_scan_job_handler(
    photo_repo: PhotoRepository,
    library_root_repo: LibraryRootRepository,
    grace_period_days: int = 30,
    scheduler: TaskScheduler | None = None,
    capabilities: Sequence[Capability] = (),
) -> Callable[[JobContext], Awaitable[None]]:
    """`scheduler`/`capabilities` are optional so degraded mode (zero models
    installed, SDD §16.4) and existing tests that only exercise scanning
    keep working unchanged: with no capabilities to run, or no scheduler to
    enqueue through, scanning simply doesn't trigger analysis afterward.
    """

    async def handler(ctx: JobContext) -> None:
        raw_library_root_id = ctx.params.get("library_root_id")
        if not isinstance(raw_library_root_id, str):
            raise ValueError("scan job requires a string 'library_root_id' param")
        library_root_id = uuid.UUID(raw_library_root_id)

        root = await library_root_repo.get(library_root_id)
        if root is None:
            raise ValueError(f"library root {library_root_id} not found")

        root_path = Path(root.path)
        is_local = is_local_path(root_path)

        discovered = _discover_files(root_path)
        total = len(discovered)

        existing_rows = await _fetch_all_existing_photos(photo_repo, library_root_id)
        existing = [
            ExistingPhoto(
                photo_id=row.id,
                relative_path=row.relative_path,
                relative_path_folded=row.relative_path_folded,
                content_hash=row.content_hash,
                size_bytes=row.size_bytes,
                file_mtime=row.file_mtime,
            )
            for row in existing_rows
        ]

        classifications = classify_changes(discovered, existing, is_local=is_local)

        matched_photo_ids: set[uuid.UUID] = set()
        photos_needing_analysis: list[uuid.UUID] = []
        for index, classification in enumerate(classifications):
            if ctx.is_cancelled():
                return
            photo_id = await _apply_classification(photo_repo, library_root_id, classification)
            matched_photo_ids.add(photo_id)
            if classification.kind in (ChangeKind.NEW, ChangeKind.MODIFIED):
                photos_needing_analysis.append(photo_id)
            await ctx.complete_item(index, total, file_id=photo_id)

        await _reconcile_absent_photos(
            photo_repo, existing_rows, matched_photo_ids, grace_period_days
        )

        if scheduler is not None and capabilities and photos_needing_analysis:
            await scheduler.enqueue(
                JobSpec(
                    job_type=ANALYSIS_JOB_TYPE,
                    params={
                        "photo_ids": [str(photo_id) for photo_id in photos_needing_analysis],
                        "capabilities": [capability.value for capability in capabilities],
                    },
                )
            )

    return handler
