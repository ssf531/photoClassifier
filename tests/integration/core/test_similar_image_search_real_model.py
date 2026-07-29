import asyncio
from argparse import Namespace
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from core.domain.search import SearchQuery, TextSearchHit
from core.domain.settings import models_dir
from core.infrastructure.ai_result_repository import EmbeddingRefRepository
from core.infrastructure.clip_embedding_provider import ClipEmbeddingProvider
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.plugin_models import Plugin
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.embedding_service import DefaultEmbeddingService
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.plugin_repository import PluginRepository
from core.infrastructure.search_service import DefaultSearchService
from core.infrastructure.vec_embedding_index import SqliteVecEmbeddingIndex

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "clip"

pytestmark = pytest.mark.skipif(
    not ClipEmbeddingProvider(models_dir(), asyncio.Semaphore(1)).is_available(),
    reason="CLIP model not downloaded into the local model cache (TASK-0C acquisition path)",
)


class _NullTextSearchIndex:
    """Not exercised by similar_to-mode queries; satisfies the constructor."""

    async def search(self, query: str, *, limit: int, offset: int = 0) -> list[TextSearchHit]:
        return []


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.cmd_opts = Namespace(x=[f"db_path={db_path}"])
    return cfg


class _Env:
    def __init__(
        self, search_service: DefaultSearchService, make_photo: Callable[[str], Awaitable[Photo]]
    ) -> None:
        self.search_service = search_service
        self.make_photo = make_photo


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    db_path = tmp_path / "similar_image_search_real.db"
    await asyncio.to_thread(command.upgrade, _alembic_config(db_path), "head")

    engine = create_engine(db_path)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    photo_repo = PhotoRepository(sessions, writer)
    library_root_repo = LibraryRootRepository(sessions, writer)
    embedding_refs = EmbeddingRefRepository(sessions, writer)
    plugin_repo = PluginRepository(sessions, writer)
    vec_index = SqliteVecEmbeddingIndex(sessions, writer)
    clip_provider = ClipEmbeddingProvider(models_dir(), asyncio.Semaphore(1))

    root = await library_root_repo.create(LibraryRoot(path=str(FIXTURES_DIR)))
    await plugin_repo.upsert(
        Plugin(
            id=clip_provider.provider_id,
            name="CLIP",
            capability_types="embedding",
            version="1.0.0",
            source="builtin",
            enabled=True,
        )
    )

    embedding_service = DefaultEmbeddingService(
        providers={"clip": clip_provider},
        index=vec_index,
        embedding_refs=embedding_refs,
        photo_repo=photo_repo,
        library_root_repo=library_root_repo,
        default_provider="clip",
    )
    search_service = DefaultSearchService(
        text_index=_NullTextSearchIndex(),
        embedding_index=vec_index,
        embedding_service=embedding_service,
        read_sessions=sessions,
        default_embedding_provider="clip",
    )

    async def make_photo(relative_path: str) -> Photo:
        now = datetime.now(timezone.utc)  # noqa: UP017 -- pre-3.11 alias pending broader migration
        photo = await photo_repo.create(
            Photo(
                library_root_id=root.id,
                relative_path=relative_path,
                relative_path_folded=relative_path.lower(),
                size_bytes=1,
                file_mtime=now,
                status="active",
            )
        )
        await embedding_service.embed(photo.id, "clip")
        return photo

    try:
        yield _Env(search_service, make_photo)
    finally:
        await writer.close()
        await engine.dispose()


async def test_similar_to_ranks_the_visually_similar_photo_above_unrelated_ones(
    env: _Env,
) -> None:
    red = await env.make_photo("red.png")
    red_copy = await env.make_photo("red_copy.png")
    blue = await env.make_photo("blue.png")
    green = await env.make_photo("green.png")

    result = await env.search_service.search(
        SearchQuery(mode="similar_to", reference_photo_id=red.id, limit=10)
    )

    ranked_ids = [r.photo_id for r in result.results]
    assert ranked_ids[0] == red_copy.id
    assert set(ranked_ids[1:]) == {blue.id, green.id}
    assert red.id not in ranked_ids  # the query photo itself is excluded
