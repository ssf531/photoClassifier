import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from core.domain.plugins import Capability
from core.domain.scheduler import JobID, JobProgress, JobSpec, JobStatus
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.job_models import Job, JobItem
from core.infrastructure.db.plugin_models import Plugin  # noqa: F401 -- registers `plugin`
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.problems_service import ProblemsService
from core.infrastructure.scheduler import JobItemRepository, JobRepository


class _FakeScheduler:
    def __init__(self) -> None:
        self.enqueued: list[JobSpec] = []

    async def enqueue(self, job: JobSpec) -> JobID:
        self.enqueued.append(job)
        return uuid.uuid4()

    async def cancel(self, job_id: JobID) -> None:
        raise NotImplementedError

    def progress_stream(self) -> AsyncIterator[JobProgress]:
        raise NotImplementedError


class _Env:
    def __init__(
        self,
        service: ProblemsService,
        item_repo: JobItemRepository,
        job_repo: JobRepository,
        scheduler: _FakeScheduler,
    ) -> None:
        self.service = service
        self.item_repo = item_repo
        self.job_repo = job_repo
        self.scheduler = scheduler

    async def make_failed_item(
        self, photo_id: uuid.UUID, error_code: str, error_message: str
    ) -> JobItem:
        job = await self.job_repo.create(
            Job(
                job_type="analysis",
                status=JobStatus.PARTIALLY_COMPLETED.value,
                progress_pct=100.0,
                params={},
            )
        )
        return await self.item_repo.create(
            JobItem(
                job_id=job.id,
                file_id=photo_id,
                status="failed",
                error_code=error_code,
                error_message=error_message,
            )
        )


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "problems.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    item_repo = JobItemRepository(sessions, writer)
    job_repo = JobRepository(sessions, writer)
    scheduler = _FakeScheduler()
    service = ProblemsService(item_repo, scheduler, [Capability.CAPTION, Capability.TAG])

    try:
        yield _Env(service, item_repo, job_repo, scheduler)
    finally:
        await writer.close()
        await engine.dispose()


async def test_list_problems_groups_by_error_code(env: _Env) -> None:
    photo_a, photo_b, photo_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await env.make_failed_item(photo_a, "capability_unavailable", "no model")
    await env.make_failed_item(photo_b, "capability_unavailable", "no model")
    await env.make_failed_item(photo_c, "provider_error", "boom")

    groups = await env.service.list_problems()

    by_code = {group.error_code: {item.photo_id for item in group.items} for group in groups}
    assert by_code == {
        "capability_unavailable": {photo_a, photo_b},
        "provider_error": {photo_c},
    }


async def test_list_problems_excludes_ignored_items(env: _Env) -> None:
    photo_id = uuid.uuid4()
    item = await env.make_failed_item(photo_id, "provider_error", "boom")
    await env.item_repo.mark_ignored([item.id])

    assert await env.service.list_problems() == []


async def test_list_problems_shows_only_the_latest_failure_per_photo(env: _Env) -> None:
    """A photo retried and failed more than once accumulates multiple failed
    `job_item` rows; the Problems view should surface only the most recent
    one, not stale duplicates."""
    photo_id = uuid.uuid4()
    await env.make_failed_item(photo_id, "provider_error", "first failure")
    await env.make_failed_item(photo_id, "capability_unavailable", "second failure")

    groups = await env.service.list_problems()

    assert len(groups) == 1
    assert groups[0].error_code == "capability_unavailable"
    assert groups[0].items[0].error_message == "second failure"


async def test_retry_enqueues_an_analysis_job_with_the_configured_capabilities(
    env: _Env,
) -> None:
    photo_ids = [uuid.uuid4(), uuid.uuid4()]

    await env.service.retry(photo_ids)

    assert len(env.scheduler.enqueued) == 1
    spec = env.scheduler.enqueued[0]
    assert spec.job_type == "analysis"
    assert set(spec.params["photo_ids"]) == {str(photo_id) for photo_id in photo_ids}
    assert spec.params["capabilities"] == ["caption", "tag"]


async def test_ignore_removes_photos_from_the_problems_list(env: _Env) -> None:
    photo_id = uuid.uuid4()
    await env.make_failed_item(photo_id, "provider_error", "boom")

    await env.service.ignore([photo_id])

    assert await env.service.list_problems() == []


async def test_ignore_only_affects_the_requested_photos(env: _Env) -> None:
    ignored_photo = uuid.uuid4()
    remaining_photo = uuid.uuid4()
    await env.make_failed_item(ignored_photo, "provider_error", "boom")
    await env.make_failed_item(remaining_photo, "provider_error", "boom")

    await env.service.ignore([ignored_photo])

    groups = await env.service.list_problems()
    assert len(groups) == 1
    assert {item.photo_id for item in groups[0].items} == {remaining_photo}
