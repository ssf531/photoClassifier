import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.api.app import create_app
from core.domain.scheduler import JobID, JobProgress, JobSpec
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository

TOKEN = "known-token"


class _FakeScheduler:
    def __init__(self) -> None:
        self.enqueued: list[JobSpec] = []
        self._next_job_id = uuid.uuid4()

    async def enqueue(self, job: JobSpec) -> JobID:
        self.enqueued.append(job)
        return self._next_job_id

    async def cancel(self, job_id: JobID) -> None:  # pragma: no cover
        raise NotImplementedError

    async def progress_stream(self) -> AsyncIterator[JobProgress]:  # pragma: no cover
        raise NotImplementedError
        yield


class _Env:
    def __init__(self, client: TestClient, scheduler: _FakeScheduler, library_root_id: str) -> None:
        self.client = client
        self.scheduler = scheduler
        self.library_root_id = library_root_id


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "scan.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)
    repo = LibraryRootRepository(sessions, writer)
    root = await repo.create(LibraryRoot(path="C:/Photos"))

    scheduler = _FakeScheduler()
    app = create_app(token=TOKEN, scheduler=scheduler, library_root_repo=repo)
    client = TestClient(app)

    try:
        yield _Env(client, scheduler, str(root.id))
    finally:
        await writer.close()
        await engine.dispose()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_trigger_scan_requires_auth(env: _Env) -> None:
    response = env.client.post("/api/v1/scan", json={"library_root_id": env.library_root_id})

    assert response.status_code == 401


def test_trigger_scan_enqueues_a_scan_job_for_the_given_root(env: _Env) -> None:
    response = env.client.post(
        "/api/v1/scan",
        json={"library_root_id": env.library_root_id},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["job_id"]
    assert len(env.scheduler.enqueued) == 1
    assert env.scheduler.enqueued[0].job_type == "scan"
    assert env.scheduler.enqueued[0].params == {"library_root_id": env.library_root_id}


def test_trigger_scan_404s_for_unknown_library_root(env: _Env) -> None:
    response = env.client.post(
        "/api/v1/scan",
        json={"library_root_id": "00000000-0000-0000-0000-000000000000"},
        headers=_auth_headers(),
    )

    assert response.status_code == 404
    assert env.scheduler.enqueued == []


def test_trigger_scan_returns_503_when_not_configured() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.post(
        "/api/v1/scan",
        json={"library_root_id": "00000000-0000-0000-0000-000000000000"},
        headers=_auth_headers(),
    )

    assert response.status_code == 503
