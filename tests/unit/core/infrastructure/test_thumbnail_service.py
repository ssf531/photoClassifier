import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.domain.thumbnails import ThumbSize
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.metadata_repository import MetadataRepository
from core.infrastructure.raster_thumbnail import ThumbnailResult
from core.infrastructure.raster_thumbnail import generate_thumbnail as real_generate_thumbnail
from core.infrastructure.thumbnail_cache import ThumbnailCacheManager
from core.infrastructure.thumbnail_service import (
    PhotoNotFoundError,
    PhotoNotHashedError,
    ThumbnailService,
)

METADATA_FIXTURES = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "metadata"


class _Env:
    def __init__(
        self,
        service: ThumbnailService,
        photo_repo: PhotoRepository,
        library_root_repo: LibraryRootRepository,
    ) -> None:
        self.service = service
        self.photo_repo = photo_repo
        self.library_root_repo = library_root_repo


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "thumb.db")
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

    try:
        yield _Env(service, photo_repo, library_root_repo)
    finally:
        await writer.close()
        await engine.dispose()


async def _make_photo(
    env: _Env, *, relative_path: str = "canon.jpg", content_hash: str | None = "abc123"
) -> Photo:
    root = await env.library_root_repo.create(LibraryRoot(path=str(METADATA_FIXTURES)))
    return await env.photo_repo.create(
        Photo(
            library_root_id=root.id,
            relative_path=relative_path,
            relative_path_folded=relative_path.lower(),
            content_hash=content_hash,
            size_bytes=1,
            file_mtime=datetime.now(timezone.utc),  # noqa: UP017
            status="active",
        )
    )


async def test_raises_photo_not_found_for_unknown_id(env: _Env) -> None:
    with pytest.raises(PhotoNotFoundError):
        await env.service.get_or_generate(uuid.uuid4(), ThumbSize.GRID)


async def test_raises_photo_not_hashed_when_content_hash_is_none(env: _Env) -> None:
    photo = await _make_photo(env, content_hash=None)

    with pytest.raises(PhotoNotHashedError):
        await env.service.get_or_generate(photo.id, ThumbSize.GRID)


async def test_generates_thumbnail_and_returns_stable_etag(env: _Env) -> None:
    photo = await _make_photo(env)

    outcome = await env.service.get_or_generate(photo.id, ThumbSize.GRID)

    assert outcome.path is not None
    assert outcome.path.is_file()
    assert outcome.etag == '"abc123-grid"'
    assert outcome.degraded_reason is None


async def test_grid_and_preview_are_cached_separately(env: _Env) -> None:
    photo = await _make_photo(env)

    grid = await env.service.get_or_generate(photo.id, ThumbSize.GRID)
    preview = await env.service.get_or_generate(photo.id, ThumbSize.PREVIEW)

    assert grid.path != preview.path
    assert grid.etag != preview.etag


async def test_concurrent_requests_for_same_photo_coalesce_to_one_generation(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    photo = await _make_photo(env)
    call_count = 0

    def counting_generate(source_path: Path, max_dimension: int) -> ThumbnailResult:
        nonlocal call_count
        call_count += 1
        return real_generate_thumbnail(source_path, max_dimension)

    monkeypatch.setattr(
        "core.infrastructure.thumbnail_service.generate_thumbnail", counting_generate
    )

    results = await asyncio.gather(
        env.service.get_or_generate(photo.id, ThumbSize.GRID),
        env.service.get_or_generate(photo.id, ThumbSize.GRID),
        env.service.get_or_generate(photo.id, ThumbSize.GRID),
    )

    assert call_count == 1
    assert {r.path for r in results} == {results[0].path}
