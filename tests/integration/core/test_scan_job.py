import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest

from core.domain.library import FileStatus
from core.domain.scheduler import JobSpec, JobStatus
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.scan_job import SCAN_JOB_TYPE, _utcnow, create_scan_job_handler
from core.infrastructure.scheduler import (
    InProcessTaskScheduler,
    JobItemRepository,
    JobRepository,
)

TERMINAL_STATUSES = {
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.PARTIALLY_COMPLETED,
    JobStatus.CANCELLED,
}


async def _run_scan_to_completion(
    scheduler: InProcessTaskScheduler, library_root_id: uuid.UUID
) -> None:
    job_id = await scheduler.enqueue(
        JobSpec(job_type=SCAN_JOB_TYPE, params={"library_root_id": str(library_root_id)})
    )
    async for event in scheduler.progress_stream():
        if event.job_id == job_id and event.status in TERMINAL_STATUSES:
            assert event.status == JobStatus.COMPLETED
            break


class _Repos:
    def __init__(
        self,
        library_root_repo: LibraryRootRepository,
        photo_repo: PhotoRepository,
        job_repo: JobRepository,
        item_repo: JobItemRepository,
    ) -> None:
        self.library_root_repo = library_root_repo
        self.photo_repo = photo_repo
        self.job_repo = job_repo
        self.item_repo = item_repo
        self.scheduler = self.new_scheduler()

    def new_scheduler(self, *, grace_period_days: int = 30) -> InProcessTaskScheduler:
        scheduler = InProcessTaskScheduler(self.job_repo, self.item_repo)
        scheduler.register_handler(
            SCAN_JOB_TYPE,
            create_scan_job_handler(
                self.photo_repo, self.library_root_repo, grace_period_days=grace_period_days
            ),
        )
        return scheduler


@pytest.fixture
async def repos(tmp_path: Path) -> AsyncIterator[_Repos]:
    engine = create_engine(tmp_path / "scan.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    library_root_repo = LibraryRootRepository(sessions, writer)
    photo_repo = PhotoRepository(sessions, writer)
    job_repo = JobRepository(sessions, writer)
    item_repo = JobItemRepository(sessions, writer)

    result = _Repos(library_root_repo, photo_repo, job_repo, item_repo)

    try:
        yield result
    finally:
        await writer.close()
        await engine.dispose()


async def test_scan_job_discovers_and_persists_photos(tmp_path: Path, repos: _Repos) -> None:
    library_dir = tmp_path / "library"
    library_dir.mkdir()
    for i in range(5):
        (library_dir / f"photo_{i}.jpg").write_bytes(b"x")

    root = await repos.library_root_repo.create(LibraryRoot(path=str(library_dir)))
    job_id = await repos.scheduler.enqueue(
        JobSpec(job_type=SCAN_JOB_TYPE, params={"library_root_id": str(root.id)})
    )

    async for event in repos.scheduler.progress_stream():
        if event.job_id == job_id and event.status in TERMINAL_STATUSES:
            break

    photos = await repos.photo_repo.list_by_library_root(root.id, limit=100, offset=0)
    assert len(photos) == 5
    assert all(p.status == FileStatus.ACTIVE.value for p in photos)


async def test_cancel_mid_scan_stops_processing_and_keeps_prior_results(
    tmp_path: Path, repos: _Repos
) -> None:
    library_dir = tmp_path / "library"
    library_dir.mkdir()
    for i in range(30):
        (library_dir / f"photo_{i:03d}.jpg").write_bytes(b"x")

    root = await repos.library_root_repo.create(LibraryRoot(path=str(library_dir)))
    job_id = await repos.scheduler.enqueue(
        JobSpec(job_type=SCAN_JOB_TYPE, params={"library_root_id": str(root.id)})
    )

    events = []
    async for event in repos.scheduler.progress_stream():
        if event.job_id != job_id:
            continue
        events.append(event)
        if len(events) == 5:
            await repos.scheduler.cancel(job_id)
        if event.status in TERMINAL_STATUSES:
            break

    assert events[-1].status == JobStatus.CANCELLED

    photos = await repos.photo_repo.list_by_library_root(root.id, limit=100, offset=0)
    assert 0 < len(photos) < 30
    assert all(p.status == FileStatus.ACTIVE.value for p in photos)


async def test_absent_file_is_marked_missing_after_scan(tmp_path: Path, repos: _Repos) -> None:
    library_dir = tmp_path / "library"
    library_dir.mkdir()
    photo_path = library_dir / "a.jpg"
    photo_path.write_bytes(b"x")

    root = await repos.library_root_repo.create(LibraryRoot(path=str(library_dir)))
    await _run_scan_to_completion(repos.scheduler, root.id)

    (photos_before,) = await repos.photo_repo.list_by_library_root(root.id, limit=10, offset=0)
    assert photos_before.status == FileStatus.ACTIVE.value

    photo_path.unlink()
    await _run_scan_to_completion(repos.scheduler, root.id)

    (photo_after,) = await repos.photo_repo.list_by_library_root(root.id, limit=10, offset=0)
    assert photo_after.id == photos_before.id
    assert photo_after.status == FileStatus.MISSING.value


async def test_missing_file_reverts_to_active_when_it_reappears(
    tmp_path: Path, repos: _Repos
) -> None:
    library_dir = tmp_path / "library"
    library_dir.mkdir()
    photo_path = library_dir / "a.jpg"
    photo_path.write_bytes(b"original content")

    root = await repos.library_root_repo.create(LibraryRoot(path=str(library_dir)))
    await _run_scan_to_completion(repos.scheduler, root.id)
    (created,) = await repos.photo_repo.list_by_library_root(root.id, limit=10, offset=0)

    photo_path.unlink()
    await _run_scan_to_completion(repos.scheduler, root.id)
    (missing,) = await repos.photo_repo.list_by_library_root(root.id, limit=10, offset=0)
    assert missing.status == FileStatus.MISSING.value

    photo_path.write_bytes(b"original content")
    await _run_scan_to_completion(repos.scheduler, root.id)

    (reappeared,) = await repos.photo_repo.list_by_library_root(root.id, limit=10, offset=0)
    assert reappeared.id == created.id
    assert reappeared.status == FileStatus.ACTIVE.value
    assert reappeared.content_hash == created.content_hash


async def test_absent_file_marked_deleted_after_grace_period_elapses(
    tmp_path: Path, repos: _Repos
) -> None:
    library_dir = tmp_path / "library"
    library_dir.mkdir()
    photo_path = library_dir / "a.jpg"
    photo_path.write_bytes(b"x")

    root = await repos.library_root_repo.create(LibraryRoot(path=str(library_dir)))
    await _run_scan_to_completion(repos.scheduler, root.id)
    (created,) = await repos.photo_repo.list_by_library_root(root.id, limit=10, offset=0)

    created.last_seen_at = _utcnow() - timedelta(days=31)
    await repos.photo_repo.update(created)

    photo_path.unlink()
    scheduler = repos.new_scheduler(grace_period_days=30)
    await _run_scan_to_completion(scheduler, root.id)

    (photo_after,) = await repos.photo_repo.list_by_library_root(root.id, limit=10, offset=0)
    assert photo_after.status == FileStatus.DELETED.value
