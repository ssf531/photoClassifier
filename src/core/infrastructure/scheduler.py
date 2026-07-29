import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

from core.domain.scheduler import JobID, JobProgress, JobSpec, JobStatus
from core.infrastructure.db.job_models import Job, JobItem
from core.infrastructure.db.repository import SqlAlchemyRepository


class JobRepository(SqlAlchemyRepository[Job]):
    model = Job


class JobItemRepository(SqlAlchemyRepository[JobItem]):
    model = JobItem


class JobContext:
    def __init__(
        self,
        job_id: JobID,
        params: dict[str, object],
        cancel_event: asyncio.Event,
        item_repo: JobItemRepository,
        report_progress: Callable[[float], Awaitable[None]],
    ) -> None:
        self.job_id = job_id
        self.params = params
        self._cancel_event = cancel_event
        self._item_repo = item_repo
        self._report_progress = report_progress

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    async def complete_item(self, index: int, total: int, file_id: uuid.UUID | None = None) -> None:
        await self._item_repo.create(
            JobItem(job_id=self.job_id, file_id=file_id, status="completed")
        )
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
        job_id = record.id
        self._cancel_events[job_id] = asyncio.Event()
        task = asyncio.create_task(self._run(job_id, job))
        self._running_tasks.add(task)
        task.add_done_callback(self._running_tasks.discard)
        return job_id

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

    async def _run(self, job_id: JobID, job: JobSpec) -> None:
        handler = self._handlers.get(job.job_type)
        if handler is None:
            await self._set_status(job_id, JobStatus.FAILED, 0.0)
            return

        await self._set_status(job_id, JobStatus.RUNNING, 0.0)
        cancel_event = self._cancel_events[job_id]

        async def report_progress(pct: float) -> None:
            await self._set_status(job_id, JobStatus.RUNNING, pct)

        ctx = JobContext(job_id, job.params, cancel_event, self._item_repo, report_progress)
        try:
            await handler(ctx)
        except Exception:
            await self._set_status(job_id, JobStatus.FAILED, 0.0)
            return

        if cancel_event.is_set():
            await self._set_status(job_id, JobStatus.CANCELLED, 0.0)
        else:
            await self._set_status(job_id, JobStatus.COMPLETED, 100.0)
