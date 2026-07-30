import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.api.app import create_app
from core.domain.search import SearchQuery, SearchResult, SearchResults
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo

# ai_result's FK to plugin.id must be registered on Base.metadata before
# create_all() runs; nothing else in this test imports plugin_models.
from core.infrastructure.db.plugin_models import Plugin as _Plugin  # noqa: F401
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository

TOKEN = "known-token"


class _FakeSearchService:
    def __init__(self, results: SearchResults) -> None:
        self._results = results
        self.received_query: SearchQuery | None = None

    async def search(self, query: SearchQuery) -> SearchResults:
        self.received_query = query
        return self._results


class _Env:
    def __init__(
        self, client: TestClient, service: _FakeSearchService, photo_ids: list[str]
    ) -> None:
        self.client = client
        self.service = service
        self.photo_ids = photo_ids


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "search.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    library_root_repo = LibraryRootRepository(sessions, writer)
    photo_repo = PhotoRepository(sessions, writer)

    root = await library_root_repo.create(LibraryRoot(path="/library"))
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration

    photo_ids = []
    for i in range(3):
        photo = await photo_repo.create(
            Photo(
                library_root_id=root.id,
                relative_path=f"photo-{i}.jpg",
                relative_path_folded=f"photo-{i}.jpg",
                size_bytes=1,
                file_mtime=now,
                status="active",
                captured_at_utc=now,
            )
        )
        photo_ids.append(str(photo.id))

    # Deliberately out of creation order, to prove the endpoint preserves
    # the service's rank order rather than re-deriving its own.
    fake_results = SearchResults(
        results=[
            SearchResult(photo_id=uuid.UUID(photo_ids[2]), score=0.9),
            SearchResult(photo_id=uuid.UUID(photo_ids[0]), score=0.5),
        ]
    )
    service = _FakeSearchService(fake_results)

    app = create_app(token=TOKEN, photo_repo=photo_repo, search_service=service)
    client = TestClient(app)

    try:
        yield _Env(client, service, photo_ids)
    finally:
        await writer.close()
        await engine.dispose()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_search_requires_auth(env: _Env) -> None:
    response = env.client.post("/api/v1/search", json={"text": "beach"})

    assert response.status_code == 401


def test_search_preserves_the_services_rank_order(env: _Env) -> None:
    response = env.client.post(
        "/api/v1/search", json={"text": "beach sunset"}, headers=_auth_headers()
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [env.photo_ids[2], env.photo_ids[0]]
    assert [item["score"] for item in body["items"]] == [0.9, 0.5]


def test_search_converts_the_request_into_a_correctly_shaped_search_query(env: _Env) -> None:
    payload = {
        "text": "beach sunset",
        "filters": {
            "date_range": {"start": "2024-01-01T00:00:00Z", "end": "2024-12-31T00:00:00Z"},
            "camera_model": "EOS R5",
            "min_rating": 3,
            "gps_bbox": {"min_lat": 1.0, "max_lat": 2.0, "min_lon": 3.0, "max_lon": 4.0},
        },
        "mode": "hybrid",
        "limit": 25,
        "offset": 5,
    }

    response = env.client.post("/api/v1/search", json=payload, headers=_auth_headers())

    assert response.status_code == 200
    query = env.service.received_query
    assert query is not None
    assert query.text == "beach sunset"
    assert query.mode == "hybrid"
    assert query.limit == 25
    assert query.offset == 5
    assert query.filters is not None
    assert query.filters.camera_model == "EOS R5"
    assert query.filters.min_rating == 3
    assert query.filters.gps_bbox is not None
    assert query.filters.gps_bbox.min_lat == 1.0
    assert query.filters.date_range is not None
    assert query.filters.date_range.start is not None


def test_search_defaults_to_hybrid_mode_and_empty_filters(env: _Env) -> None:
    response = env.client.post("/api/v1/search", json={"text": "beach"}, headers=_auth_headers())

    assert response.status_code == 200
    query = env.service.received_query
    assert query is not None
    assert query.mode == "hybrid"
    assert query.filters is None


def test_search_returns_503_when_not_configured() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.post("/api/v1/search", json={"text": "beach"}, headers=_auth_headers())

    assert response.status_code == 503
