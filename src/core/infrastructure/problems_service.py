import uuid
from collections.abc import Sequence

from core.domain.plugins import Capability
from core.domain.problems import ProblemGroup, ProblemItem
from core.domain.scheduler import JobID, JobSpec, TaskScheduler
from core.infrastructure.analysis_job import ANALYSIS_JOB_TYPE
from core.infrastructure.db.job_models import JobItem
from core.infrastructure.scheduler import JobItemRepository

_LIST_ALL_FAILED_PAGE_SIZE = 500


class ProblemsService:
    """SDD §16.3's Problems view: surfaces `job_item` failures grouped by
    `error_code` with "retry these" and "ignore permanently" actions --
    without it, a 0.5% failure rate across 100,000 photos is 500 invisible
    gaps in the index.
    """

    def __init__(
        self,
        item_repo: JobItemRepository,
        scheduler: TaskScheduler,
        retry_capabilities: Sequence[Capability],
    ) -> None:
        self._items = item_repo
        self._scheduler = scheduler
        self._retry_capabilities = list(retry_capabilities)

    async def list_problems(self) -> list[ProblemGroup]:
        latest_by_photo = await self._latest_active_failure_per_photo()

        grouped: dict[str, list[ProblemItem]] = {}
        for item in latest_by_photo.values():
            assert item.file_id is not None
            assert item.error_code is not None
            grouped.setdefault(item.error_code, []).append(
                ProblemItem(photo_id=item.file_id, error_message=item.error_message or "")
            )
        return [
            ProblemGroup(error_code=error_code, items=items)
            for error_code, items in grouped.items()
        ]

    async def retry(self, photo_ids: Sequence[uuid.UUID]) -> JobID:
        return await self._scheduler.enqueue(
            JobSpec(
                job_type=ANALYSIS_JOB_TYPE,
                params={
                    "photo_ids": [str(photo_id) for photo_id in photo_ids],
                    "capabilities": [capability.value for capability in self._retry_capabilities],
                },
            )
        )

    async def ignore(self, photo_ids: Sequence[uuid.UUID]) -> None:
        latest_by_photo = await self._latest_active_failure_per_photo()
        requested = set(photo_ids)
        job_item_ids = [
            item.id for photo_id, item in latest_by_photo.items() if photo_id in requested
        ]
        await self._items.mark_ignored(job_item_ids)

    async def _latest_active_failure_per_photo(self) -> dict[uuid.UUID, JobItem]:
        """Every not-yet-ignored failed `job_item`, deduped to the single
        most recent occurrence per photo -- a photo retried more than once
        can accumulate several failed rows across separate jobs, but only
        its latest failure is an "active" problem.
        """
        latest: dict[uuid.UUID, JobItem] = {}
        offset = 0
        while True:
            page = await self._items.list_failed(limit=_LIST_ALL_FAILED_PAGE_SIZE, offset=offset)
            for item in page:
                if item.file_id is None:
                    continue
                existing = latest.get(item.file_id)
                if existing is None or item.created_at > existing.created_at:
                    latest[item.file_id] = item
            if len(page) < _LIST_ALL_FAILED_PAGE_SIZE:
                return latest
            offset += _LIST_ALL_FAILED_PAGE_SIZE
