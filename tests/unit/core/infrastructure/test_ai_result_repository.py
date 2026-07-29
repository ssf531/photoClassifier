import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.infrastructure.ai_result_repository import AiResultRepository, EmbeddingRefRepository
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.plugin_models import Plugin
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.plugin_repository import PluginRepository


class _Env:
    def __init__(
        self,
        ai_results: AiResultRepository,
        embeddings: EmbeddingRefRepository,
        photo_id: uuid.UUID,
        plugin_id: str,
    ) -> None:
        self.ai_results = ai_results
        self.embeddings = embeddings
        self.photo_id = photo_id
        self.plugin_id = plugin_id


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "ai_result.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    photo_repo = PhotoRepository(sessions, writer)
    library_root_repo = LibraryRootRepository(sessions, writer)
    plugin_repo = PluginRepository(sessions, writer)

    root = await library_root_repo.create(LibraryRoot(path="/library"))
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    photo = await photo_repo.create(
        Photo(
            library_root_id=root.id,
            relative_path="a.jpg",
            relative_path_folded="a.jpg",
            size_bytes=1,
            file_mtime=now,
            status="active",
        )
    )
    await plugin_repo.upsert(
        Plugin(
            id="clip-embedding",
            name="CLIP",
            capability_types="embedding",
            version="1.0.0",
            source="builtin",
            enabled=True,
        )
    )
    await plugin_repo.upsert(
        Plugin(
            id="other-tag",
            name="Other Tagger",
            capability_types="tag",
            version="1.0.0",
            source="builtin",
            enabled=True,
        )
    )

    try:
        yield _Env(
            AiResultRepository(sessions, writer),
            EmbeddingRefRepository(sessions, writer),
            photo.id,
            "clip-embedding",
        )
    finally:
        await writer.close()
        await engine.dispose()


async def test_record_result_creates_a_current_row(env: _Env) -> None:
    result = await env.ai_results.record_result(
        photo_id=env.photo_id,
        plugin_id=env.plugin_id,
        capability="tag",
        model_version="clip-vit-b32@1",
        payload={"tags": ["dog"]},
        confidence=0.9,
    )

    assert result.is_current is True


async def test_recording_twice_leaves_exactly_one_current_row(env: _Env) -> None:
    await env.ai_results.record_result(
        photo_id=env.photo_id,
        plugin_id=env.plugin_id,
        capability="tag",
        model_version="clip-vit-b32@1",
        payload={"tags": ["dog"]},
        confidence=0.9,
    )
    await env.ai_results.record_result(
        photo_id=env.photo_id,
        plugin_id=env.plugin_id,
        capability="tag",
        model_version="clip-vit-b32@2",
        payload={"tags": ["dog", "outdoors"]},
        confidence=0.95,
    )

    current = await env.ai_results.list_current_by_photo(env.photo_id)

    assert len(current) == 1
    assert current[0].model_version == "clip-vit-b32@2"


async def test_a_different_plugin_keeps_its_own_independent_current_row(env: _Env) -> None:
    await env.ai_results.record_result(
        photo_id=env.photo_id,
        plugin_id=env.plugin_id,
        capability="tag",
        model_version="clip-vit-b32@1",
        payload={"tags": ["dog"]},
        confidence=0.9,
    )
    await env.ai_results.record_result(
        photo_id=env.photo_id,
        plugin_id="other-tag",
        capability="tag",
        model_version="other-tagger@1",
        payload={"tags": ["cat"]},
        confidence=0.8,
    )

    current = await env.ai_results.list_current_by_photo(env.photo_id)

    assert {row.plugin_id for row in current} == {env.plugin_id, "other-tag"}
    assert all(row.is_current for row in current)


async def test_upsert_embedding_creates_a_row(env: _Env) -> None:
    embedding = await env.embeddings.upsert_embedding(
        photo_id=env.photo_id,
        plugin_id=env.plugin_id,
        model_version="clip-vit-b32@1",
        vector_space="clip-vit-b32",
        vector_key=str(env.photo_id),
    )

    assert embedding.vector_space == "clip-vit-b32"


async def test_upsert_embedding_replaces_the_existing_row_for_the_same_key(env: _Env) -> None:
    first = await env.embeddings.upsert_embedding(
        photo_id=env.photo_id,
        plugin_id=env.plugin_id,
        model_version="clip-vit-b32@1",
        vector_space="clip-vit-b32",
        vector_key="key-v1",
    )
    second = await env.embeddings.upsert_embedding(
        photo_id=env.photo_id,
        plugin_id=env.plugin_id,
        model_version="clip-vit-b32@2",
        vector_space="clip-vit-b32",
        vector_key="key-v2",
    )

    assert second.id == first.id
    assert second.vector_key == "key-v2"
    assert second.model_version == "clip-vit-b32@2"
