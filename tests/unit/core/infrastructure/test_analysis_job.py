import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.domain.plugins import Capability
from core.domain.providers import ImageRef, QualityResult
from core.domain.scheduler import JobSpec, JobStatus
from core.infrastructure.ai_result_repository import AiResultRepository
from core.infrastructure.analysis_job import ANALYSIS_JOB_TYPE, create_analysis_job_handler
from core.infrastructure.analysis_pipeline import AnalysisPipeline
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.job_models import Job, JobItem
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.plugin_models import Plugin
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.plugin_repository import PluginRepository
from core.infrastructure.provider_registry import ProviderRegistry
from core.infrastructure.quality_provider import (
    PROVIDER_ID as QUALITY_PROVIDER_ID,
)
from core.infrastructure.quality_provider import QualityAssessmentProvider
from core.infrastructure.scheduler import InProcessTaskScheduler, JobItemRepository, JobRepository

QUALITY_FIXTURES = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "quality"

TERMINAL_STATUSES = {
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.PARTIALLY_COMPLETED,
    JobStatus.CANCELLED,
}


async def _quality_invoker(provider: QualityAssessmentProvider, image: ImageRef) -> QualityResult:
    return await provider.assess(image)


async def _collect_until_terminal(
    scheduler: InProcessTaskScheduler, job_id: object, timeout: float = 5.0
) -> None:
    stream = scheduler.progress_stream()

    async def _consume() -> None:
        async for event in stream:
            if event.job_id == job_id and event.status in TERMINAL_STATUSES:
                return

    await asyncio.wait_for(_consume(), timeout=timeout)


class _Env:
    def __init__(
        self,
        scheduler: InProcessTaskScheduler,
        job_repo: JobRepository,
        item_repo: JobItemRepository,
        ai_results: AiResultRepository,
        photos: list[Photo],
    ) -> None:
        self.scheduler = scheduler
        self.job_repo = job_repo
        self.item_repo = item_repo
        self.ai_results = ai_results
        self.photos = photos


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "analysis_job.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    photo_repo = PhotoRepository(sessions, writer)
    library_root_repo = LibraryRootRepository(sessions, writer)
    ai_results = AiResultRepository(sessions, writer)
    plugin_repo = PluginRepository(sessions, writer)
    job_repo = JobRepository(sessions, writer)
    item_repo = JobItemRepository(sessions, writer)

    root = await library_root_repo.create(LibraryRoot(path=str(QUALITY_FIXTURES)))
    await plugin_repo.upsert(
        Plugin(
            id=QUALITY_PROVIDER_ID,
            name="Quality",
            capability_types="quality",
            version="1.0.0",
            source="builtin",
            enabled=True,
        )
    )

    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    photos = [
        await photo_repo.create(
            Photo(
                library_root_id=root.id,
                relative_path=name,
                relative_path_folded=name.lower(),
                size_bytes=1,
                file_mtime=now,
                status="active",
            )
        )
        for name in ("sharp.png", "blurry.png", "normal.png")
    ]

    registry = ProviderRegistry({Capability.QUALITY: QualityAssessmentProvider()})
    pipeline = AnalysisPipeline(registry, ai_results, {Capability.QUALITY: _quality_invoker})
    handler = create_analysis_job_handler(pipeline, photo_repo, library_root_repo, item_repo)

    scheduler = InProcessTaskScheduler(job_repo, item_repo)
    scheduler.register_handler(ANALYSIS_JOB_TYPE, handler)

    try:
        yield _Env(scheduler, job_repo, item_repo, ai_results, photos)
    finally:
        await writer.close()
        await engine.dispose()


async def test_analysis_job_processes_all_photos_end_to_end(env: _Env) -> None:
    photo_ids = [str(p.id) for p in env.photos]
    job_id = await env.scheduler.enqueue(
        JobSpec(
            job_type=ANALYSIS_JOB_TYPE,
            params={"photo_ids": photo_ids, "capabilities": ["quality"]},
        )
    )

    await _collect_until_terminal(env.scheduler, job_id)

    job = await env.job_repo.get(job_id)
    assert job is not None
    assert job.status == JobStatus.COMPLETED.value
    for photo in env.photos:
        result = await env.ai_results.list_current_by_photo(photo.id)
        assert len(result) == 1


async def test_resuming_after_a_simulated_crash_skips_completed_photos_and_does_not_duplicate(
    env: _Env,
) -> None:
    photo1, photo2, photo3 = env.photos

    # Simulate "photo1 finished processing before the crash": a real
    # ai_result row plus the job_item bookkeeping that marks it done.
    await env.ai_results.record_result(
        photo_id=photo1.id,
        plugin_id=QUALITY_PROVIDER_ID,
        capability="quality",
        model_version="laplacian-exposure@1",
        payload={"sharpness_variance": 999.0},
        confidence=1.0,
    )
    stale_job = await env.job_repo.create(
        Job(
            job_type=ANALYSIS_JOB_TYPE,
            status=JobStatus.RUNNING.value,
            progress_pct=33.0,
            params={
                "photo_ids": [str(photo1.id), str(photo2.id), str(photo3.id)],
                "capabilities": ["quality"],
            },
        )
    )
    await env.item_repo.create(JobItem(job_id=stale_job.id, file_id=photo1.id, status="completed"))

    await env.scheduler.resume_incomplete_jobs()
    await _collect_until_terminal(env.scheduler, stale_job.id)

    job = await env.job_repo.get(stale_job.id)
    assert job is not None
    assert job.status == JobStatus.COMPLETED.value

    items = await env.item_repo.list_by_job(stale_job.id, limit=10, offset=0)
    assert len(items) == 3
    assert {item.file_id for item in items} == {photo1.id, photo2.id, photo3.id}

    # photo1 must not have been reprocessed: exactly one ai_result row ever, not two.
    photo1_versions = await env.ai_results.list_all_versions_by_photo(photo1.id)
    assert len(photo1_versions) == 1
    assert photo1_versions[0].payload == {"sharpness_variance": 999.0}

    for photo in (photo2, photo3):
        current = await env.ai_results.list_current_by_photo(photo.id)
        assert len(current) == 1
