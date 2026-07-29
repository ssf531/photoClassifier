import asyncio
from argparse import Namespace
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
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
from core.infrastructure.vec_embedding_index import SqliteVecEmbeddingIndex

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "clip"

pytestmark = pytest.mark.skipif(
    not ClipEmbeddingProvider(models_dir(), asyncio.Semaphore(1)).is_available(),
    reason="CLIP model not downloaded into the local model cache (TASK-0C acquisition path)",
)


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.cmd_opts = Namespace(x=[f"db_path={db_path}"])
    return cfg


class _Env:
    def __init__(
        self,
        service: DefaultEmbeddingService,
        index: SqliteVecEmbeddingIndex,
        make_photo: Callable[[str], Awaitable[Photo]],
    ) -> None:
        self.service = service
        self.index = index
        self.make_photo = make_photo


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    db_path = tmp_path / "embedding_service_real.db"
    await asyncio.to_thread(command.upgrade, _alembic_config(db_path), "head")

    engine = create_engine(db_path)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    photo_repo = PhotoRepository(sessions, writer)
    library_root_repo = LibraryRootRepository(sessions, writer)
    embedding_refs = EmbeddingRefRepository(sessions, writer)
    plugin_repo = PluginRepository(sessions, writer)
    index = SqliteVecEmbeddingIndex(sessions, writer)
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

    service = DefaultEmbeddingService(
        providers={"clip": clip_provider},
        index=index,
        embedding_refs=embedding_refs,
        photo_repo=photo_repo,
        library_root_repo=library_root_repo,
        default_provider="clip",
    )

    async def make_photo(relative_path: str) -> Photo:
        now = datetime.now(timezone.utc)  # noqa: UP017 -- pre-3.11 alias pending broader migration
        return await photo_repo.create(
            Photo(
                library_root_id=root.id,
                relative_path=relative_path,
                relative_path_folded=relative_path.lower(),
                size_bytes=1,
                file_mtime=now,
                status="active",
            )
        )

    try:
        yield _Env(service, index, make_photo)
    finally:
        await writer.close()
        await engine.dispose()


async def test_similar_to_ranks_the_same_color_photo_above_a_different_one(env: _Env) -> None:
    red_a = await env.make_photo("red.png")
    red_b = await env.make_photo("red_copy.png")  # a second photo of the same visual content
    blue = await env.make_photo("blue.png")

    await env.service.embed(red_a.id, "clip")
    await env.service.embed(red_b.id, "clip")
    await env.service.embed(blue.id, "clip")

    results = await env.service.similar_to(red_a.id, k=2)

    assert [r.photo_id for r in results] == [red_b.id, blue.id]
    assert results[0].score > results[1].score


async def test_embed_text_finds_the_matching_color_photo_via_similarity(env: _Env) -> None:
    red = await env.make_photo("red.png")
    blue = await env.make_photo("blue.png")
    await env.service.embed(red.id, "clip")
    await env.service.embed(blue.id, "clip")

    query_vector = await env.service.embed_text("a photo of the color red", "clip")
    hits = await env.index.query(query_vector, vector_space="clip", limit=2)

    assert hits[0].photo_id == red.id
