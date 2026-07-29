import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.domain.library import PhotoId
from core.domain.providers import ImageRef, Vector
from core.domain.search import VectorSearchHit
from core.infrastructure.ai_result_repository import EmbeddingRefRepository
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.plugin_models import Plugin
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.embedding_service import (
    DefaultEmbeddingService,
    PhotoNotEmbeddedError,
    PhotoNotFoundError,
    UnknownEmbeddingProviderError,
)
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.plugin_repository import PluginRepository


@dataclass(frozen=True)
class _FakeEmbeddingProvider:
    provider_id: str
    model_version: str
    image_vector: Vector
    text_vector: Vector = field(default_factory=lambda: [0.0])

    async def embed_image(self, image: ImageRef) -> Vector:
        return self.image_vector

    async def embed_text(self, text: str) -> Vector:
        return self.text_vector


class _FakeEmbeddingIndex:
    def __init__(self) -> None:
        self._store: dict[str, tuple[str, PhotoId, Vector]] = {}

    async def upsert(
        self, *, vector_key: str, vector_space: str, photo_id: PhotoId, vector: Vector
    ) -> None:
        self._store[vector_key] = (vector_space, photo_id, vector)

    async def delete(self, vector_key: str) -> None:
        self._store.pop(vector_key, None)

    async def get(self, vector_key: str) -> Vector | None:
        entry = self._store.get(vector_key)
        return entry[2] if entry is not None else None

    async def query(
        self, vector: Vector, *, vector_space: str, limit: int
    ) -> list[VectorSearchHit]:
        candidates = [
            (photo_id, stored_vector)
            for space, photo_id, stored_vector in self._store.values()
            if space == vector_space
        ]
        scored = sorted(
            ((photo_id, _cosine(vector, v)) for photo_id, v in candidates),
            key=lambda item: item[1],
            reverse=True,
        )
        return [
            VectorSearchHit(photo_id=photo_id, score=score) for photo_id, score in scored[:limit]
        ]


def _cosine(a: Vector, b: Vector) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


class _Env:
    def __init__(
        self,
        service: DefaultEmbeddingService,
        index: _FakeEmbeddingIndex,
        photo_repo: PhotoRepository,
        library_root_repo: LibraryRootRepository,
        embedding_refs: EmbeddingRefRepository,
        library_root_id: uuid.UUID,
    ) -> None:
        self.service = service
        self.index = index
        self.photo_repo = photo_repo
        self.library_root_repo = library_root_repo
        self.embedding_refs = embedding_refs
        self.library_root_id = library_root_id


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "embedding_service.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    photo_repo = PhotoRepository(sessions, writer)
    library_root_repo = LibraryRootRepository(sessions, writer)
    embedding_refs = EmbeddingRefRepository(sessions, writer)
    plugin_repo = PluginRepository(sessions, writer)
    root = await library_root_repo.create(LibraryRoot(path="/library"))
    await plugin_repo.upsert(
        Plugin(
            id="fake-clip",
            name="Fake CLIP",
            capability_types="embedding",
            version="1.0.0",
            source="builtin",
            enabled=True,
        )
    )

    index = _FakeEmbeddingIndex()
    provider = _FakeEmbeddingProvider(
        provider_id="fake-clip", model_version="fake-clip@1", image_vector=[1.0, 0.0]
    )
    service = DefaultEmbeddingService(
        providers={"clip": provider},
        index=index,
        embedding_refs=embedding_refs,
        photo_repo=photo_repo,
        library_root_repo=library_root_repo,
        default_provider="clip",
    )

    try:
        yield _Env(service, index, photo_repo, library_root_repo, embedding_refs, root.id)
    finally:
        await writer.close()
        await engine.dispose()


async def _make_photo(env: _Env, relative_path: str = "a.jpg") -> Photo:
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    return await env.photo_repo.create(
        Photo(
            library_root_id=env.library_root_id,
            relative_path=relative_path,
            relative_path_folded=relative_path.lower(),
            size_bytes=1,
            file_mtime=now,
            status="active",
        )
    )


async def test_embed_upserts_into_the_index(env: _Env) -> None:
    photo = await _make_photo(env)

    await env.service.embed(photo.id, "clip")

    vector = await env.index.get(f"{photo.id}:clip")
    assert vector == [1.0, 0.0]


async def test_embed_raises_for_unknown_photo(env: _Env) -> None:
    with pytest.raises(PhotoNotFoundError):
        await env.service.embed(uuid.uuid4(), "clip")


async def test_embed_raises_for_unknown_provider(env: _Env) -> None:
    photo = await _make_photo(env)

    with pytest.raises(UnknownEmbeddingProviderError):
        await env.service.embed(photo.id, "does-not-exist")


async def test_similar_to_raises_when_photo_has_no_embedding(env: _Env) -> None:
    photo = await _make_photo(env)

    with pytest.raises(PhotoNotEmbeddedError):
        await env.service.similar_to(photo.id, k=5)


async def test_similar_to_excludes_the_query_photo_itself(env: _Env) -> None:
    photo = await _make_photo(env, "a.jpg")
    other = await _make_photo(env, "b.jpg")
    await env.service.embed(photo.id, "clip")
    await env.index.upsert(
        vector_key=f"{other.id}:clip", vector_space="clip", photo_id=other.id, vector=[0.9, 0.1]
    )

    results = await env.service.similar_to(photo.id, k=5)

    assert [r.photo_id for r in results] == [other.id]


async def test_embed_text_delegates_to_the_named_provider(env: _Env) -> None:
    provider = _FakeEmbeddingProvider(
        provider_id="fake-clip",
        model_version="fake-clip@1",
        image_vector=[1.0, 0.0],
        text_vector=[0.5, 0.5],
    )
    service = DefaultEmbeddingService(
        providers={"clip": provider},
        index=env.index,
        embedding_refs=env.embedding_refs,
        photo_repo=env.photo_repo,
        library_root_repo=env.library_root_repo,
        default_provider="clip",
    )

    vector = await service.embed_text("a red circle", "clip")

    assert vector == [0.5, 0.5]
