import asyncio
from dataclasses import replace

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.domain.search import (
    EmbeddingIndex,
    EmbeddingService,
    MetadataFilters,
    SearchQuery,
    SearchResult,
    SearchResults,
    TextSearchIndex,
)
from core.infrastructure.metadata_filters import filter_photo_ids
from core.infrastructure.rank_fusion import reciprocal_rank_fusion


class InvalidSearchQueryError(Exception):
    pass


class DefaultSearchService:
    """Unifies metadata filters, full-text query, and vector similarity into
    ranked results (SDD §4.6/§7). `hybrid` runs the text and semantic
    branches concurrently, over-fetching each to `limit + offset` with its
    own offset zeroed, then combines them with Reciprocal Rank Fusion (SDD
    §7.2) before applying the outer query's offset/limit once to the fused
    ranking -- offset must apply to the *fused* order, not be baked into
    each branch's own internal slice.
    """

    def __init__(
        self,
        text_index: TextSearchIndex,
        embedding_index: EmbeddingIndex,
        embedding_service: EmbeddingService,
        read_sessions: async_sessionmaker[AsyncSession],
        default_embedding_provider: str,
    ) -> None:
        self._text_index = text_index
        self._embedding_index = embedding_index
        self._embedding_service = embedding_service
        self._read_sessions = read_sessions
        self._default_embedding_provider = default_embedding_provider

    async def search(self, query: SearchQuery) -> SearchResults:
        if query.mode == "metadata":
            return await self._search_metadata(query)
        if query.mode == "text":
            return await self._search_text(query)
        if query.mode == "semantic":
            return await self._search_semantic(query)
        if query.mode == "similar_to":
            return await self._search_similar_to(query)
        if query.mode == "hybrid":
            return await self._search_hybrid(query)
        raise InvalidSearchQueryError(f"unknown search mode: {query.mode!r}")

    async def _search_metadata(self, query: SearchQuery) -> SearchResults:
        ids = await filter_photo_ids(
            self._read_sessions,
            query.filters or MetadataFilters(),
            limit=query.limit,
            offset=query.offset,
        )
        # no ranking signal in pure metadata browsing; every match counts equally
        return SearchResults([SearchResult(photo_id=pid, score=1.0) for pid in ids])

    async def _search_text(self, query: SearchQuery) -> SearchResults:
        if query.text is None:
            raise InvalidSearchQueryError("text mode requires query.text")
        hits = await self._text_index.search(query.text, limit=query.limit, offset=query.offset)
        results = [SearchResult(photo_id=hit.photo_id, score=hit.score) for hit in hits]
        return await self._apply_filters(results, query)

    async def _search_semantic(self, query: SearchQuery) -> SearchResults:
        if query.text is None:
            raise InvalidSearchQueryError("semantic mode requires query.text")
        vector = await self._embedding_service.embed_text(
            query.text, self._default_embedding_provider
        )
        hits = await self._embedding_index.query(
            vector,
            vector_space=self._default_embedding_provider,
            limit=query.limit + query.offset,
        )
        results = [
            SearchResult(photo_id=hit.photo_id, score=hit.score) for hit in hits[query.offset :]
        ]
        return await self._apply_filters(results, query)

    async def _search_similar_to(self, query: SearchQuery) -> SearchResults:
        if query.reference_photo_id is None:
            raise InvalidSearchQueryError("similar_to mode requires query.reference_photo_id")
        scored = await self._embedding_service.similar_to(
            query.reference_photo_id, k=query.limit + query.offset
        )
        results = [SearchResult(photo_id=s.photo_id, score=s.score) for s in scored[query.offset :]]
        return await self._apply_filters(results, query)

    async def _search_hybrid(self, query: SearchQuery) -> SearchResults:
        if query.text is None:
            raise InvalidSearchQueryError("hybrid mode requires query.text")

        branch_query = replace(query, offset=0, limit=query.limit + query.offset)
        text_results, semantic_results = await asyncio.gather(
            self._search_text(replace(branch_query, mode="text")),
            self._search_semantic(replace(branch_query, mode="semantic")),
        )

        fused = reciprocal_rank_fusion(
            [
                [r.photo_id for r in text_results.results],
                [r.photo_id for r in semantic_results.results],
            ]
        )
        page = fused[query.offset : query.offset + query.limit]
        return SearchResults([SearchResult(photo_id=pid, score=score) for pid, score in page])

    async def _apply_filters(
        self, results: list[SearchResult], query: SearchQuery
    ) -> SearchResults:
        if query.filters is None or not results:
            return SearchResults(results)
        allowed = await filter_photo_ids(
            self._read_sessions,
            query.filters,
            limit=len(results),
            offset=0,
            candidate_ids=[r.photo_id for r in results],
        )
        allowed_set = set(allowed)
        return SearchResults([r for r in results if r.photo_id in allowed_set])
