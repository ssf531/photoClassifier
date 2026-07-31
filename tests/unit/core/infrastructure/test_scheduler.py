import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from core.domain.scheduler import JobSpec, JobStatus
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.job_models import Job, JobItem
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.scheduler import (
    InProcessTaskScheduler,
    JobContext,
    JobItemRepository,
    JobRepository,
)

TERMINAL_STATUSES = {
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.PARTIALLY_COMPLETED,
    JobStatus.CANCELLED,
}


@pytest.fixture
async def scheduler(tmp_path: Path) -> AsyncIterator[InProcessTaskScheduler]:
    engine = create_engine(tmp_path / "scheduler.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)
    job_repo = JobRepository(sessions, writer)
    item_repo = JobItemRepository(sessions, writer)
    try:
        yield InProcessTaskScheduler(job_repo, item_repo)
    finally:
        await writer.close()
        await engine.dispose()


async def _collect_until_terminal(
    scheduler: InProcessTaskScheduler, job_id: object, timeout: float = 5.0
) -> list:
    events = []
    stream = scheduler.progress_stream()

    async def _consume() -> None:
        async for event in stream:
            if event.job_id == job_id:
                events.append(event)
                if event.status in TERMINAL_STATUSES:
                    return

    await asyncio.wait_for(_consume(), timeout=timeout)
    return events


async def test_noop_job_reaches_completed_and_emits_progress(
    scheduler: InProcessTaskScheduler,
) -> None:
    job_id = await scheduler.enqueue(JobSpec(job_type="noop", params={"item_count": 3}))

    events = await _collect_until_terminal(scheduler, job_id)

    assert len(events) >= 1
    assert events[-1].status == JobStatus.COMPLETED
    assert events[-1].progress_pct == 100.0

    job = await scheduler._job_repo.get(job_id)
    assert job is not None
    assert job.status == JobStatus.COMPLETED.value

    items = await scheduler._item_repo.list(limit=10, offset=0)
    assert len(items) == 3


async def test_unknown_job_type_fails(scheduler: InProcessTaskScheduler) -> None:
    job_id = await scheduler.enqueue(JobSpec(job_type="does-not-exist"))

    events = await _collect_until_terminal(scheduler, job_id)

    assert events[-1].status == JobStatus.FAILED


async def test_cancel_stops_remaining_items(scheduler: InProcessTaskScheduler) -> None:
    job_id = await scheduler.enqueue(JobSpec(job_type="noop", params={"item_count": 1000}))
    await scheduler.cancel(job_id)

    events = await _collect_until_terminal(scheduler, job_id)

    assert events[-1].status == JobStatus.CANCELLED
    items = await scheduler._item_repo.list(limit=2000, offset=0)
    assert len(items) < 1000


async def test_resume_incomplete_jobs_reruns_a_job_left_running_by_a_crash(
    scheduler: InProcessTaskScheduler,
) -> None:
    # Simulate a crash: a `job` row stuck in RUNNING with no in-memory task
    # behind it (never went through enqueue() in this process).
    stale_job = await scheduler._job_repo.create(
        Job(job_type="noop", status=JobStatus.RUNNING.value, progress_pct=40.0, params={})
    )

    await scheduler.resume_incomplete_jobs()
    events = await _collect_until_terminal(scheduler, stale_job.id)

    assert events[-1].status == JobStatus.COMPLETED


async def test_a_job_with_a_failed_item_completes_as_partially_completed(
    scheduler: InProcessTaskScheduler,
) -> None:
    async def handler(ctx: JobContext) -> None:
        await ctx.complete_item(0, 2)
        await ctx.fail_item(1, 2, "some_error", "it broke")

    scheduler.register_handler("partial", handler)
    job_id = await scheduler.enqueue(JobSpec(job_type="partial"))

    events = await _collect_until_terminal(scheduler, job_id)

    assert events[-1].status == JobStatus.PARTIALLY_COMPLETED
    job = await scheduler._job_repo.get(job_id)
    assert job is not None
    assert job.status == JobStatus.PARTIALLY_COMPLETED.value

    items = await scheduler._item_repo.list_by_job(job_id, limit=10, offset=0)
    failed = [item for item in items if item.status == "failed"]
    assert len(failed) == 1
    assert failed[0].error_code == "some_error"
    assert failed[0].error_message == "it broke"


async def test_resuming_a_job_that_already_recorded_a_failure_stays_partially_completed(
    scheduler: InProcessTaskScheduler,
) -> None:
    stale_job = await scheduler._job_repo.create(
        Job(
            job_type="noop",
            status=JobStatus.RUNNING.value,
            progress_pct=50.0,
            params={"item_count": 1},
        )
    )
    await scheduler._item_repo.create(
        JobItem(
            job_id=stale_job.id, file_id=None, status="failed", error_code="x", error_message="y"
        )
    )

    await scheduler.resume_incomplete_jobs()
    events = await _collect_until_terminal(scheduler, stale_job.id)

    assert events[-1].status == JobStatus.PARTIALLY_COMPLETED


async def test_resume_incomplete_jobs_is_a_noop_when_nothing_is_running(
    scheduler: InProcessTaskScheduler,
) -> None:
    job_id = await scheduler.enqueue(JobSpec(job_type="noop", params={"item_count": 1}))
    await _collect_until_terminal(scheduler, job_id)  # let it finish before resuming

    await scheduler.resume_incomplete_jobs()  # must not raise or duplicate anything

    jobs = await scheduler._job_repo.list(limit=10, offset=0)
    assert len(jobs) == 1
