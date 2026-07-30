from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.api.app import create_app
from core.domain.library import FileStatus
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo

# ai_result's FK to plugin.id must be registered on Base.metadata before
# create_all() runs (core.api.app imports AiResultRepository transitively);
# nothing else in this test imports plugin_models.
from core.infrastructure.db.plugin_models import Plugin as _Plugin  # noqa: F401
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository

TOKEN = "known-token"


class _Env:
    def __init__(self, client: TestClient, photo_ids: list[str]) -> None:
        self.client = client
        self.photo_ids = photo_ids


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "photo_list.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    library_root_repo = LibraryRootRepository(sessions, writer)
    photo_repo = PhotoRepository(sessions, writer)

    root = await library_root_repo.create(LibraryRoot(path="/library"))
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration

    photo_ids = []
    for i in range(5):
        photo = await photo_repo.create(
            Photo(
                library_root_id=root.id,
                relative_path=f"photo-{i}.jpg",
                relative_path_folded=f"photo-{i}.jpg",
                size_bytes=1,
                file_mtime=now,
                status="active",
                captured_at_utc=now - timedelta(days=i),
            )
        )
        photo_ids.append(str(photo.id))
    await photo_repo.create(
        Photo(
            library_root_id=root.id,
            relative_path="missing.jpg",
            relative_path_folded="missing.jpg",
            size_bytes=1,
            file_mtime=now,
            status=FileStatus.MISSING.value,
            captured_at_utc=now,
        )
    )

    app = create_app(token=TOKEN, photo_repo=photo_repo)
    client = TestClient(app)

    try:
        yield _Env(client, photo_ids)
    finally:
        await writer.close()
        await engine.dispose()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_list_photos_requires_auth(env: _Env) -> None:
    response = env.client.get("/api/v1/photos")

    assert response.status_code == 401


def test_list_photos_returns_active_photos_newest_first(env: _Env) -> None:
    response = env.client.get("/api/v1/photos?limit=10", headers=_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == env.photo_ids
    assert body["next_offset"] is None


def test_list_photos_paginates_with_next_offset(env: _Env) -> None:
    first_page = env.client.get("/api/v1/photos?limit=2&offset=0", headers=_auth_headers()).json()
    second_page = env.client.get("/api/v1/photos?limit=2&offset=2", headers=_auth_headers()).json()

    assert [item["id"] for item in first_page["items"]] == env.photo_ids[0:2]
    assert first_page["next_offset"] == 2
    assert [item["id"] for item in second_page["items"]] == env.photo_ids[2:4]
    assert second_page["next_offset"] == 4


def test_list_photos_rejects_a_limit_outside_the_allowed_range(env: _Env) -> None:
    response = env.client.get("/api/v1/photos?limit=0", headers=_auth_headers())

    assert response.status_code == 422


def test_list_photos_returns_503_when_repository_not_configured() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.get("/api/v1/photos", headers=_auth_headers())

    assert response.status_code == 503
