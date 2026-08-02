import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.domain.search import TextSearchHit

_SHADOW_TABLES = ("ai_result_fts", "photo_fts", "metadata_fts")

# A per-table ceiling on how many of a table's best matches ever get pulled
# into Python before scores are summed across tables and sorted. Without
# this, a common query term (e.g. one word that appears in a large fraction
# of captions) has no LIMIT at all and materializes an unbounded fraction
# of the whole library -- generous enough that any realistic top-N page is
# extremely unlikely to be affected by the cap.
_MAX_MATCHES_PER_TABLE = 5000


class FtsTextSearchIndex:
    """Queries the FTS5 shadow tables from TASK-032 (SDD §3.6/§7.3): each
    table is queried independently since they shadow different source
    tables, then relevance is combined by summing each match's bm25 rank
    (negated, since FTS5's bm25() is more-negative-is-better) across
    surfaces -- a photo matching in more than one (e.g. filename AND
    caption) ranks higher than one matching in just one.
    """

    def __init__(self, read_sessions: async_sessionmaker[AsyncSession]) -> None:
        self._read_sessions = read_sessions

    async def search(self, query: str, *, limit: int, offset: int = 0) -> list[TextSearchHit]:
        fts_query = _sanitize_fts_query(query)
        if not fts_query:
            return []

        scores: dict[uuid.UUID, float] = {}
        async with self._read_sessions() as session:
            for table in _SHADOW_TABLES:
                query_sql = (
                    f"SELECT photo_id, bm25({table}) AS rank FROM {table} "
                    f"WHERE {table} MATCH :q ORDER BY rank LIMIT :cap"
                )
                result = await session.execute(
                    text(query_sql), {"q": fts_query, "cap": _MAX_MATCHES_PER_TABLE}
                )
                for photo_id_hex, rank in result.all():
                    photo_id = uuid.UUID(photo_id_hex)
                    scores[photo_id] = scores.get(photo_id, 0.0) + (-rank)

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        page = ranked[offset : offset + limit]
        return [TextSearchHit(photo_id=photo_id, score=score) for photo_id, score in page]


def _sanitize_fts_query(query: str) -> str:
    """Quote each whitespace-separated word as its own FTS5 phrase literal
    (implicitly AND-ed together), so arbitrary user input -- hyphens,
    colons, asterisks, parens -- can never be parsed as FTS5 query-syntax
    operators. The tokenizer still splits each phrase's contents normally,
    so this changes nothing about what matches, only what can crash."""
    quote = '"'
    words = query.split()
    escaped = [quote + word.replace(quote, quote + quote) + quote for word in words]
    return " ".join(escaped)
