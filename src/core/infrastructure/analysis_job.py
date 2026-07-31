import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from core.domain.plugins import Capability
from core.domain.providers import ImageRef
from core.infrastructure.analysis_pipeline import AnalysisPipeline
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.scheduler import JobContext, JobItemRepository

ANALYSIS_JOB_TYPE = "analysis"
_PAGE_SIZE = 500


async def _completed_photo_ids(item_repo: JobItemRepository, job_id: uuid.UUID) -> set[uuid.UUID]:
    """Every photo this job has already recorded a job_item for -- the
    resume mechanism (SDD §11.2): re-invoking this handler after a crash
    must skip whatever committed before the crash, never redo it."""
    completed: set[uuid.UUID] = set()
    offset = 0
    while True:
        page = await item_repo.list_by_job(job_id, limit=_PAGE_SIZE, offset=offset)
        completed.update(item.file_id for item in page if item.file_id is not None)
        if len(page) < _PAGE_SIZE:
            return completed
        offset += _PAGE_SIZE


async def _resolve_image(
    photo_repo: PhotoRepository, library_root_repo: LibraryRootRepository, photo_id: uuid.UUID
) -> ImageRef | None:
    photo = await photo_repo.get(photo_id)
    if photo is None:
        return None
    root = await library_root_repo.get(photo.library_root_id)
    if root is None:
        return None
    return ImageRef(photo_id=photo_id, path=Path(root.path) / photo.relative_path)


def create_analysis_job_handler(
    pipeline: AnalysisPipeline,
    photo_repo: PhotoRepository,
    library_root_repo: LibraryRootRepository,
    item_repo: JobItemRepository,
) -> Callable[[JobContext], Awaitable[None]]:
    """Wires `AnalysisPipeline.run_batch()` into the Task Scheduler as
    durable job/job_item rows (SDD §11.2): a crash mid-batch resumes only
    the photos not yet recorded as completed job_items, and re-running an
    already-current `ai_result` row is safe (append-and-flip, SDD §5.4), so
    no special de-duplication is needed beyond skipping completed items.
    """

    async def handler(ctx: JobContext) -> None:
        raw_photo_ids = ctx.params.get("photo_ids")
        if not isinstance(raw_photo_ids, list):
            raise ValueError("analysis job requires a list 'photo_ids' param")
        photo_ids = [uuid.UUID(raw_id) for raw_id in raw_photo_ids]

        raw_capabilities = ctx.params.get("capabilities")
        if not isinstance(raw_capabilities, list):
            raise ValueError("analysis job requires a list 'capabilities' param")
        capabilities = [Capability(raw_capability) for raw_capability in raw_capabilities]

        already_completed = await _completed_photo_ids(item_repo, ctx.job_id)
        total = len(photo_ids)

        for index, photo_id in enumerate(photo_ids):
            if ctx.is_cancelled():
                return
            if photo_id in already_completed:
                continue

            image = await _resolve_image(photo_repo, library_root_repo, photo_id)
            if image is None:
                await ctx.fail_item(
                    index,
                    total,
                    "photo_not_found",
                    f"photo {photo_id} could not be resolved to a file on disk",
                    file_id=photo_id,
                )
                continue

            report = await pipeline.run_batch([image], capabilities)
            if report.failures:
                first = report.failures[0]
                message = first.error_message
                if len(report.failures) > 1:
                    message = f"{message} (+{len(report.failures) - 1} more capability failure(s))"
                await ctx.fail_item(index, total, first.error_code, message, file_id=photo_id)
            else:
                await ctx.complete_item(index, total, file_id=photo_id)

    return handler
