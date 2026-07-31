import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from core.domain.scheduler import JobID, JobProgress, JobSpec, JobStatus
from core.infrastructure.db.job_models import Job, JobItem
from core.infrastructure.db.repository import SqlAlchemyRepository


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration


class JobRepository(SqlAlchemyRepository[Job]):
    model = Job

    async def list_by_status(self, status: JobStatus, *, limit: int, offset: int) -> list[Job]:
        async with self._read_sessions() as session:
            result = await session.execute(
                select(Job)
                .where(Job.status == status.value)
                .order_by(Job.id)
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())


class JobItemRepository(SqlAlchemyRepository[JobItem]):
    model = JobItem

    async def list_by_job(self, job_id: JobID, *, limit: int, offset: int) -> list[JobItem]:
        async with self._read_sessions() as session:
            result = await session.execute(
                select(JobItem)
                .where(JobItem.job_id == job_id)
                .order_by(JobItem.id)
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    async def has_failed_item(self, job_id: JobID) -> bool:
        """Used on resume-after-crash (SDD §11.2) to correctly re-seed
        `JobContext.has_failures()`: a job that already recorded a failure
        before the crash must still resolve to `PARTIALLY_COMPLETED`, not
        `COMPLETED`, once resumed."""
        async with self._read_sessions() as session:
            result = await session.execute(
                select(JobItem.id)
                .where(JobItem.job_id == job_id, JobItem.status == "failed")
                .limit(1)
            )
            return result.scalar_one_or_none() is not None

    async def list_failed(self, *, limit: int, offset: int) -> list[JobItem]:
        """Every not-yet-ignored failed job_item across all jobs, most
        recent first (SDD §16.3's Problems view)."""
        async with self._read_sessions() as session:
            result = await session.execute(
                select(JobItem)
                .where(JobItem.status == "failed", JobItem.ignored_at.is_(None))
                .order_by(JobItem.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    async def mark_ignored(self, job_item_ids: Sequence[uuid.UUID]) -> None:
        now = _utcnow()
        for job_item_id in job_item_ids:
            item = await self.get(job_item_id)
            if item is not None:
                item.ignored_at = now
                await self.update(item)


class JobContext:
    def __init__(
        self,
        job_id: JobID,
        params: dict[str, object],
        cancel_event: asyncio.Event,
        item_repo: JobItemRepository,
        report_progress: Callable[[float], Awaitable[None]],
        *,
        had_prior_failures: bool = False,
    ) -> None:
        self.job_id = job_id
        self.params = params
        self._cancel_event = cancel_event
        self._item_repo = item_repo
        self._report_progress = report_progress
        self._had_failures = had_prior_failures

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def has_failures(self) -> bool:
        return self._had_failures

    async def complete_item(self, index: int, total: int, file_id: uuid.UUID | None = None) -> None:
        await self._item_repo.create(
            JobItem(job_id=self.job_id, file_id=file_id, status="completed")
        )
        await self._report_progress((index + 1) / total * 100)

    async def fail_item(
        self,
        index: int,
        total: int,
        error_code: str,
        error_message: str,
        file_id: uuid.UUID | None = None,
    ) -> None:
        await self._item_repo.create(
            JobItem(
                job_id=self.job_id,
                file_id=file_id,
                status="failed",
                error_code=error_code,
                error_message=error_message,
            )
        )
        self._had_failures = True
        await self._report_progress((index + 1) / total * 100)


JobHandler = Callable[[JobContext], Awaitable[None]]


async def noop_handler(ctx: JobContext) -> None:
    item_count = ctx.params.get("item_count", 1)
    total = item_count if isinstance(item_count, int) else 1
    for i in range(total):
        if ctx.is_cancelled():
            return
        await asyncio.sleep(0)
        await ctx.complete_item(i, total)


class InProcessTaskScheduler:
    def __init__(self, job_repo: JobRepository, item_repo: JobItemRepository) -> None:
        self._job_repo = job_repo
        self._item_repo = item_repo
        self._handlers: dict[str, JobHandler] = {"noop": noop_handler}
        self._subscribers: list[asyncio.Queue[JobProgress]] = []
        self._cancel_events: dict[JobID, asyncio.Event] = {}
        self._running_tasks: set[asyncio.Task[None]] = set()

    def register_handler(self, job_type: str, handler: JobHandler) -> None:
        self._handlers[job_type] = handler

    async def enqueue(self, job: JobSpec) -> JobID:
        record = await self._job_repo.create(
            Job(
                job_type=job.job_type,
                status=JobStatus.QUEUED.value,
                progress_pct=0.0,
                params=job.params,
            )
        )
        self._start(record.id, job.job_type, job.params)
        return record.id

    async def resume_incomplete_jobs(self) -> None:
        """Re-invoke any job an unclean shutdown left in RUNNING state (SDD
        §11.2). Safe to call unconditionally at startup even if nothing
        crashed: a handler that finds every item already completed (via its
        own job_item bookkeeping) simply finishes immediately.
        """
        stale_jobs = await self._job_repo.list_by_status(JobStatus.RUNNING, limit=1000, offset=0)
        for job in stale_jobs:
            self._start(job.id, job.job_type, job.params)

    def _start(self, job_id: JobID, job_type: str, params: dict[str, Any]) -> None:
        self._cancel_events[job_id] = asyncio.Event()
        task = asyncio.create_task(self._run(job_id, job_type, params))
        self._running_tasks.add(task)
        task.add_done_callback(self._running_tasks.discard)

    async def cancel(self, job_id: JobID) -> None:
        event = self._cancel_events.get(job_id)
        if event is not None:
            event.set()

    def progress_stream(self) -> AsyncIterator[JobProgress]:
        queue: asyncio.Queue[JobProgress] = asyncio.Queue()
        self._subscribers.append(queue)
        return self._stream_from(queue)

    async def _stream_from(self, queue: asyncio.Queue[JobProgress]) -> AsyncIterator[JobProgress]:
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.remove(queue)

    async def _publish(self, progress: JobProgress) -> None:
        for queue in list(self._subscribers):
            await queue.put(progress)

    async def _set_status(self, job_id: JobID, status: JobStatus, progress_pct: float) -> None:
        record = await self._job_repo.get(job_id)
        if record is None:
            return
        record.status = status.value
        record.progress_pct = progress_pct
        await self._job_repo.update(record)
        await self._publish(
            JobProgress(
                job_id=job_id,
                job_type=record.job_type,
                status=status,
                progress_pct=progress_pct,
            )
        )

    async def _run(self, job_id: JobID, job_type: str, params: dict[str, Any]) -> None:
        handler = self._handlers.get(job_type)
        if handler is None:
            await self._set_status(job_id, JobStatus.FAILED, 0.0)
            return

        await self._set_status(job_id, JobStatus.RUNNING, 0.0)
        cancel_event = self._cancel_events[job_id]

        async def report_progress(pct: float) -> None:
            await self._set_status(job_id, JobStatus.RUNNING, pct)

        had_prior_failures = await self._item_repo.has_failed_item(job_id)
        ctx = JobContext(
            job_id,
            params,
            cancel_event,
            self._item_repo,
            report_progress,
            had_prior_failures=had_prior_failures,
        )
        try:
            await handler(ctx)
        except Exception:
            await self._set_status(job_id, JobStatus.FAILED, 0.0)
            return

        if cancel_event.is_set():
            await self._set_status(job_id, JobStatus.CANCELLED, 0.0)
        elif ctx.has_failures():
            # SDD §16.3: a partially-failed job must complete as
            # PARTIALLY_COMPLETED, never silently as COMPLETED.
            await self._set_status(job_id, JobStatus.PARTIALLY_COMPLETED, 100.0)
        else:
            await self._set_status(job_id, JobStatus.COMPLETED, 100.0)
