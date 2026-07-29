from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.domain.providers import ImageRef, Vector
from core.domain.search import (
    MetadataFilters,
    ScoredPhoto,
    SearchQuery,
    TextSearchHit,
    VectorSearchHit,
)
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.search_service import DefaultSearchService, InvalidSearchQueryError


class _FakeTextSearchIndex:
    def __init__(self, hits: list[TextSearchHit]) -> None:
        self._hits = hits
        self.last_query: str | None = None

    async def search(self, query: str, *, limit: int, offset: int = 0) -> list[TextSearchHit]:
        self.last_query = query
        return self._hits[offset : offset + limit]


class _FakeEmbeddingIndex:
    def __init__(self, hits: list[VectorSearchHit]) -> None:
        self._hits = hits
        self.last_vector_space: str | None = None

    async def upsert(self, **kwargs: object) -> None:
        raise NotImplementedError

    async def delete(self, vector_key: str) -> None:
        raise NotImplementedError

    async def get(self, vector_key: str) -> Vector | None:
        raise NotImplementedError

    async def query(
        self, vector: Vector, *, vector_space: str, limit: int
    ) -> list[VectorSearchHit]:
        self.last_vector_space = vector_space
        return self._hits[:limit]


class _FakeEmbeddingService:
    def __init__(self, similar: list[ScoredPhoto], text_vector: Vector) -> None:
        self._similar = similar
        self._text_vector = text_vector
        self.last_embed_text_query: str | None = None

    async def embed(self, photo_id: object, provider: str) -> None:
        raise NotImplementedError

    async def similar_to(self, photo_id: object, k: int) -> list[ScoredPhoto]:
        return self._similar[:k]

    async def embed_text(self, query: str, provider: str) -> Vector:
        self.last_embed_text_query = query
        return self._text_vector

    async def embed_image(self, image: ImageRef) -> Vector:  # pragma: no cover
        raise NotImplementedError


class _Env:
    def __init__(
        self,
        service: DefaultSearchService,
        text_index: _FakeTextSearchIndex,
        embedding_index: _FakeEmbeddingIndex,
        embedding_service: _FakeEmbeddingService,
        photos: list[Photo],
    ) -> None:
        self.service = service
        self.text_index = text_index
        self.embedding_index = embedding_index
        self.embedding_service = embedding_service
        self.photos = photos


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "search_service.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    photo_repo = PhotoRepository(sessions, writer)
    library_root_repo = LibraryRootRepository(sessions, writer)
    root = await library_root_repo.create(LibraryRoot(path="/library"))

    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    photos = [
        await photo_repo.create(
            Photo(
                library_root_id=root.id,
                relative_path=f"{i}.jpg",
                relative_path_folded=f"{i}.jpg",
                size_bytes=1,
                file_mtime=now,
                status="active",
            )
        )
        for i in range(3)
    ]

    text_index = _FakeTextSearchIndex(
        [
            TextSearchHit(photo_id=photos[0].id, score=2.0),
            TextSearchHit(photo_id=photos[1].id, score=1.0),
        ]
    )
    embedding_index = _FakeEmbeddingIndex(
        [
            VectorSearchHit(photo_id=photos[1].id, score=0.9),
            VectorSearchHit(photo_id=photos[2].id, score=0.5),
        ]
    )
    embedding_service = _FakeEmbeddingService(
        similar=[ScoredPhoto(photo_id=photos[2].id, score=0.8)],
        text_vector=[1.0, 0.0],
    )

    service = DefaultSearchService(
        text_index=text_index,
        embedding_index=embedding_index,
        embedding_service=embedding_service,
        read_sessions=sessions,
        default_embedding_provider="clip",
    )

    try:
        yield _Env(service, text_index, embedding_index, embedding_service, photos)
    finally:
        await writer.close()
        await engine.dispose()


async def test_metadata_mode_dispatches_to_filter_photo_ids(env: _Env) -> None:
    result = await env.service.search(SearchQuery(mode="metadata", limit=10))

    assert {r.photo_id for r in result.results} == {p.id for p in env.photos}
    assert all(r.score == 1.0 for r in result.results)


async def test_text_mode_dispatches_to_text_index(env: _Env) -> None:
    result = await env.service.search(SearchQuery(mode="text", text="beach", limit=10))

    assert env.text_index.last_query == "beach"
    assert [r.photo_id for r in result.results] == [env.photos[0].id, env.photos[1].id]


async def test_text_mode_requires_text(env: _Env) -> None:
    with pytest.raises(InvalidSearchQueryError):
        await env.service.search(SearchQuery(mode="text", text=None))


async def test_semantic_mode_embeds_query_and_queries_the_embedding_index(env: _Env) -> None:
    result = await env.service.search(SearchQuery(mode="semantic", text="a red car", limit=10))

    assert env.embedding_service.last_embed_text_query == "a red car"
    assert env.embedding_index.last_vector_space == "clip"
    assert [r.photo_id for r in result.results] == [env.photos[1].id, env.photos[2].id]


async def test_similar_to_mode_dispatches_to_embedding_service(env: _Env) -> None:
    result = await env.service.search(
        SearchQuery(mode="similar_to", reference_photo_id=env.photos[0].id, limit=10)
    )

    assert [r.photo_id for r in result.results] == [env.photos[2].id]


async def test_similar_to_mode_requires_reference_photo_id(env: _Env) -> None:
    with pytest.raises(InvalidSearchQueryError):
        await env.service.search(SearchQuery(mode="similar_to", reference_photo_id=None))


async def test_hybrid_mode_combines_text_and_semantic_branches(env: _Env) -> None:
    result = await env.service.search(SearchQuery(mode="hybrid", text="beach", limit=10))

    scored = {r.photo_id: r.score for r in result.results}
    # photo[1] appears in both branches (1.0 from text + 0.9 from semantic)
    assert scored[env.photos[1].id] == pytest.approx(1.9)
    assert env.photos[0].id in scored
    assert env.photos[2].id in scored


async def test_unknown_mode_raises(env: _Env) -> None:
    bad_query = SearchQuery(mode="metadata")
    object.__setattr__(bad_query, "mode", "not-a-real-mode")

    with pytest.raises(InvalidSearchQueryError):
        await env.service.search(bad_query)


async def test_filters_are_applied_as_a_post_filter_on_text_results(env: _Env) -> None:
    # No photo has any user_data row, so a rating filter excludes everything --
    # proving the filter is genuinely applied on top of the text branch's hits.
    result = await env.service.search(
        SearchQuery(mode="text", text="beach", filters=MetadataFilters(min_rating=5), limit=10)
    )

    assert result.results == []
