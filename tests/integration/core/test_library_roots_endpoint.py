from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.api.app import create_app
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository

TOKEN = "known-token"


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[TestClient]:
    engine = create_engine(tmp_path / "library_roots.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)
    repo = LibraryRootRepository(sessions, writer)

    app = create_app(token=TOKEN, library_root_repo=repo)
    test_client = TestClient(app)

    try:
        yield test_client
    finally:
        await writer.close()
        await engine.dispose()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_create_library_root_requires_auth(client: TestClient) -> None:
    response = client.post("/api/v1/library-roots", json={"path": "C:/Photos"})

    assert response.status_code == 401


def test_create_library_root_creates_a_row(client: TestClient) -> None:
    response = client.post(
        "/api/v1/library-roots", json={"path": "C:/Photos"}, headers=_auth_headers()
    )

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == "C:/Photos"
    assert body["id"]


def test_create_library_root_is_idempotent_for_the_same_path(client: TestClient) -> None:
    first = client.post(
        "/api/v1/library-roots", json={"path": "C:/Photos"}, headers=_auth_headers()
    )
    second = client.post(
        "/api/v1/library-roots", json={"path": "C:/Photos"}, headers=_auth_headers()
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_create_library_root_returns_503_when_not_configured() -> None:
    app = create_app(token=TOKEN)
    no_repo_client = TestClient(app)

    response = no_repo_client.post(
        "/api/v1/library-roots", json={"path": "C:/Photos"}, headers=_auth_headers()
    )

    assert response.status_code == 503
