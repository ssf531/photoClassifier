import asyncio
import uuid
from argparse import Namespace
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command
from core.domain.providers import ImageRef, Vector
from core.infrastructure.ai_result_repository import AiResultRepository, EmbeddingRefRepository
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.plugin_models import Plugin
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.plugin_repository import PluginRepository
from core.infrastructure.reindex import rebuild_fts_index, rebuild_vector_index
from core.infrastructure.vec_embedding_index import SqliteVecEmbeddingIndex

REPO_ROOT = Path(__file__).resolve().parents[3]


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.cmd_opts = Namespace(x=[f"db_path={db_path}"])
    return cfg


class _FakeEmbeddingService:
    """Deterministic stand-in for CLIP: derives a fixed vector from the
    photo_id itself, so re-embedding the same photo always reproduces the
    same vector -- enough to prove rebuild_vector_index re-populates
    correctly without needing the real model."""

    def __init__(self) -> None:
        self.embed_calls: list[tuple[uuid.UUID, str]] = []

    async def embed(self, photo_id: uuid.UUID, provider: str) -> None:
        self.embed_calls.append((photo_id, provider))

    async def similar_to(self, photo_id: uuid.UUID, k: int) -> list[object]:  # pragma: no cover
        raise NotImplementedError

    async def embed_text(self, query: str, provider: str) -> Vector:  # pragma: no cover
        raise NotImplementedError

    async def embed_image(self, image: ImageRef) -> Vector:  # pragma: no cover
        raise NotImplementedError


class _Env:
    def __init__(
        self,
        writer: WriteConnection,
        engine: object,
        photo_repo: PhotoRepository,
        ai_results: AiResultRepository,
        embedding_refs: EmbeddingRefRepository,
        vec_index: SqliteVecEmbeddingIndex,
        photo: Photo,
        sessions: object,
    ) -> None:
        self.writer = writer
        self.engine = engine
        self.photo_repo = photo_repo
        self.ai_results = ai_results
        self.embedding_refs = embedding_refs
        self.vec_index = vec_index
        self.photo = photo
        self.sessions = sessions


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    db_path = tmp_path / "reindex.db"
    await asyncio.to_thread(command.upgrade, _alembic_config(db_path), "head")

    engine = create_engine(db_path)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    photo_repo = PhotoRepository(sessions, writer)
    library_root_repo = LibraryRootRepository(sessions, writer)
    ai_results = AiResultRepository(sessions, writer)
    embedding_refs = EmbeddingRefRepository(sessions, writer)
    plugin_repo = PluginRepository(sessions, writer)
    vec_index = SqliteVecEmbeddingIndex(sessions, writer)

    root = await library_root_repo.create(LibraryRoot(path="/library"))
    await plugin_repo.upsert(
        Plugin(
            id="blip2-caption",
            name="Captioner",
            capability_types="caption",
            version="1.0.0",
            source="builtin",
            enabled=True,
        )
    )
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    photo = await photo_repo.create(
        Photo(
            library_root_id=root.id,
            relative_path="beach-sunset.jpg",
            relative_path_folded="beach-sunset.jpg",
            size_bytes=1,
            file_mtime=now,
            status="active",
        )
    )

    try:
        yield _Env(
            writer, engine, photo_repo, ai_results, embedding_refs, vec_index, photo, sessions
        )
    finally:
        await writer.close()
        await engine.dispose()  # type: ignore[attr-defined]


async def _fts_hits(env: _Env, table: str, match: str) -> list[tuple]:
    async with env.sessions() as session:  # type: ignore[operator]
        result = await session.execute(
            text(f"SELECT * FROM {table} WHERE {table} MATCH :m"), {"m": match}
        )
        return list(result.fetchall())


async def test_rebuild_fts_index_restores_search_after_shadow_tables_are_corrupted(
    env: _Env,
) -> None:
    await env.ai_results.record_result(
        photo_id=env.photo.id,
        plugin_id="blip2-caption",
        capability="caption",
        model_version="blip2-base@1",
        payload={"caption": "a dog running on the beach"},
        confidence=0.9,
    )
    assert len(await _fts_hits(env, "photo_fts", "beach")) == 1
    assert len(await _fts_hits(env, "ai_result_fts", "dog")) == 1

    # Simulate corruption / a stale index left over from before an upgrade.
    async with env.writer.transaction() as connection:
        await connection.execute(text("DELETE FROM photo_fts"))
        await connection.execute(text("DELETE FROM ai_result_fts"))
        await connection.execute(text("DELETE FROM metadata_fts"))
    assert await _fts_hits(env, "photo_fts", "beach") == []
    assert await _fts_hits(env, "ai_result_fts", "dog") == []

    await rebuild_fts_index(env.writer)

    assert len(await _fts_hits(env, "photo_fts", "beach")) == 1
    assert len(await _fts_hits(env, "ai_result_fts", "dog")) == 1


async def test_rebuild_vector_index_reembeds_every_photo_in_embedding_ref(env: _Env) -> None:
    await env.embedding_refs.upsert_embedding(
        photo_id=env.photo.id,
        plugin_id="blip2-caption",  # any plugin row satisfies the FK for this test
        model_version="clip-vit-b32@1",
        vector_space="clip",
        vector_key=f"{env.photo.id}:clip",
    )
    fake_service = _FakeEmbeddingService()

    await rebuild_vector_index(env.embedding_refs, fake_service)

    assert fake_service.embed_calls == [(env.photo.id, "clip")]
