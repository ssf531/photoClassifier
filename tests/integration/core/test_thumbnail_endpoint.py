from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.api.app import create_app
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.metadata_repository import MetadataRepository
from core.infrastructure.thumbnail_cache import ThumbnailCacheManager
from core.infrastructure.thumbnail_service import ThumbnailService

METADATA_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "metadata"
TOKEN = "known-token"


class _Env:
    def __init__(self, client: TestClient, photo_id: str) -> None:
        self.client = client
        self.photo_id = photo_id


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "endpoint.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    photo_repo = PhotoRepository(sessions, writer)
    library_root_repo = LibraryRootRepository(sessions, writer)
    metadata_repo = MetadataRepository(sessions, writer)
    cache = ThumbnailCacheManager(tmp_path / "cache", max_size_bytes=10_000_000)
    service = ThumbnailService(
        cache, photo_repo, library_root_repo, metadata_repo, grid_size_px=100, preview_size_px=400
    )

    root = await library_root_repo.create(LibraryRoot(path=str(METADATA_FIXTURES)))
    photo = await photo_repo.create(
        Photo(
            library_root_id=root.id,
            relative_path="canon.jpg",
            relative_path_folded="canon.jpg",
            content_hash="fixedhash",
            size_bytes=1,
            file_mtime=datetime.now(timezone.utc),  # noqa: UP017
            status="active",
        )
    )

    app = create_app(token=TOKEN, thumbnail_service=service)
    client = TestClient(app)

    try:
        yield _Env(client, str(photo.id))
    finally:
        await writer.close()
        await engine.dispose()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_thumbnail_requires_auth(env: _Env) -> None:
    response = env.client.get(f"/api/v1/thumbnails/{env.photo_id}?size=grid")

    assert response.status_code == 401


def test_thumbnail_returns_jpeg_with_etag_and_immutable_cache_control(env: _Env) -> None:
    response = env.client.get(
        f"/api/v1/thumbnails/{env.photo_id}?size=grid", headers=_auth_headers()
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["etag"] == '"fixedhash-grid"'
    assert "immutable" in response.headers["cache-control"]
    assert len(response.content) > 0


def test_thumbnail_returns_304_when_etag_matches(env: _Env) -> None:
    first = env.client.get(f"/api/v1/thumbnails/{env.photo_id}?size=grid", headers=_auth_headers())
    etag = first.headers["etag"]

    second = env.client.get(
        f"/api/v1/thumbnails/{env.photo_id}?size=grid",
        headers={**_auth_headers(), "If-None-Match": etag},
    )

    assert second.status_code == 304


def test_thumbnail_404s_for_unknown_photo(env: _Env) -> None:
    response = env.client.get(
        "/api/v1/thumbnails/00000000-0000-0000-0000-000000000000?size=grid",
        headers=_auth_headers(),
    )

    assert response.status_code == 404


def test_thumbnail_grid_and_preview_are_distinct(env: _Env) -> None:
    grid = env.client.get(f"/api/v1/thumbnails/{env.photo_id}?size=grid", headers=_auth_headers())
    preview = env.client.get(
        f"/api/v1/thumbnails/{env.photo_id}?size=preview", headers=_auth_headers()
    )

    assert grid.headers["etag"] != preview.headers["etag"]


def test_thumbnail_service_not_configured_returns_503() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.get(
        "/api/v1/thumbnails/00000000-0000-0000-0000-000000000000?size=grid",
        headers=_auth_headers(),
    )

    assert response.status_code == 503
