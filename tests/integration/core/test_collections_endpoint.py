from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.api.app import create_app
from core.infrastructure.collection_manager import CollectionManager
from core.infrastructure.collection_repository import CollectionItemRepository, CollectionRepository
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository

TOKEN = "known-token"


class _Env:
    def __init__(self, client: TestClient, photo_ids: list[str]) -> None:
        self.client = client
        self.photo_ids = photo_ids


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "collections.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    library_root_repo = LibraryRootRepository(sessions, writer)
    photo_repo = PhotoRepository(sessions, writer)
    root = await library_root_repo.create(LibraryRoot(path="/library"))
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    photo_a = await photo_repo.create(
        Photo(
            library_root_id=root.id,
            relative_path="a.jpg",
            relative_path_folded="a.jpg",
            size_bytes=1,
            file_mtime=now,
            status="active",
        )
    )
    photo_b = await photo_repo.create(
        Photo(
            library_root_id=root.id,
            relative_path="b.jpg",
            relative_path_folded="b.jpg",
            size_bytes=1,
            file_mtime=now,
            status="active",
        )
    )

    manager = CollectionManager(
        CollectionRepository(sessions, writer), CollectionItemRepository(sessions, writer)
    )
    app = create_app(token=TOKEN, collection_manager=manager)
    client = TestClient(app)

    try:
        yield _Env(client, [str(photo_a.id), str(photo_b.id)])
    finally:
        await writer.close()
        await engine.dispose()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_list_collections_requires_auth(env: _Env) -> None:
    response = env.client.get("/api/v1/collections")

    assert response.status_code == 401


def test_create_then_list_collections(env: _Env) -> None:
    create_response = env.client.post(
        "/api/v1/collections", json={"name": "Trip"}, headers=_auth_headers()
    )
    assert create_response.status_code == 200
    body = create_response.json()
    assert body["name"] == "Trip"
    assert body["type"] == "virtual"
    assert body["item_count"] == 0

    list_response = env.client.get("/api/v1/collections", headers=_auth_headers())
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == body["id"]


def test_add_members_then_list_members(env: _Env) -> None:
    created = env.client.post(
        "/api/v1/collections", json={"name": "Trip"}, headers=_auth_headers()
    ).json()

    add_response = env.client.post(
        f"/api/v1/collections/{created['id']}/members",
        json={"photo_ids": env.photo_ids},
        headers=_auth_headers(),
    )
    assert add_response.status_code == 200

    members_response = env.client.get(
        f"/api/v1/collections/{created['id']}/members", headers=_auth_headers()
    )
    assert members_response.status_code == 200
    body = members_response.json()
    assert set(body["photo_ids"]) == set(env.photo_ids)
    assert body["next_offset"] is None

    list_response = env.client.get("/api/v1/collections", headers=_auth_headers())
    assert list_response.json()["items"][0]["item_count"] == 2


def test_add_members_is_idempotent_for_already_added_photos(env: _Env) -> None:
    created = env.client.post(
        "/api/v1/collections", json={"name": "Trip"}, headers=_auth_headers()
    ).json()

    for _ in range(2):
        response = env.client.post(
            f"/api/v1/collections/{created['id']}/members",
            json={"photo_ids": env.photo_ids},
            headers=_auth_headers(),
        )
        assert response.status_code == 200

    list_response = env.client.get("/api/v1/collections", headers=_auth_headers())
    assert list_response.json()["items"][0]["item_count"] == 2


def test_add_members_404s_for_unknown_collection(env: _Env) -> None:
    response = env.client.post(
        "/api/v1/collections/00000000-0000-0000-0000-000000000000/members",
        json={"photo_ids": env.photo_ids},
        headers=_auth_headers(),
    )

    assert response.status_code == 404


def test_list_members_404s_for_unknown_collection(env: _Env) -> None:
    response = env.client.get(
        "/api/v1/collections/00000000-0000-0000-0000-000000000000/members",
        headers=_auth_headers(),
    )

    assert response.status_code == 404


def test_collections_endpoints_return_503_when_not_configured() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)
    headers = _auth_headers()

    assert client.get("/api/v1/collections", headers=headers).status_code == 503
    assert (
        client.post("/api/v1/collections", json={"name": "Trip"}, headers=headers).status_code
        == 503
    )
    assert (
        client.post(
            "/api/v1/collections/00000000-0000-0000-0000-000000000000/members",
            json={"photo_ids": []},
            headers=headers,
        ).status_code
        == 503
    )
    assert (
        client.get(
            "/api/v1/collections/00000000-0000-0000-0000-000000000000/members",
            headers=headers,
        ).status_code
        == 503
    )
