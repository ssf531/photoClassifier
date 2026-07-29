import hashlib
import json
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.domain.library import PhotoId
from core.domain.providers import Vector
from core.domain.search import VectorSearchHit
from core.infrastructure.db.write_connection import WriteConnection


class SqliteVecEmbeddingIndex:
    """EmbeddingIndex over sqlite-vec's `vec0` virtual table (ADR-0003):
    vectors live in the same SQLite file as everything else, partitioned by
    `vector_space` for filtered KNN search. `vector_key` is the vendor-
    neutral key (not `lancedb_key`); vec0 requires an integer rowid, so
    rowids are derived deterministically from `vector_key` by hashing --
    re-upserting the same key always resolves to the same row, and no
    separate key->rowid mapping table is needed.
    """

    def __init__(
        self, read_sessions: async_sessionmaker[AsyncSession], writer: WriteConnection
    ) -> None:
        self._read_sessions = read_sessions
        self._writer = writer

    async def upsert(
        self, *, vector_key: str, vector_space: str, photo_id: PhotoId, vector: Vector
    ) -> None:
        rowid = _rowid_for(vector_key)
        async with self._writer.transaction() as connection:
            await connection.execute(
                text("DELETE FROM embedding_index WHERE rowid = :rowid"), {"rowid": rowid}
            )
            await connection.execute(
                text(
                    "INSERT INTO embedding_index"
                    "(rowid, embedding, vector_space, vector_key, photo_id) "
                    "VALUES (:rowid, :embedding, :vector_space, :vector_key, :photo_id)"
                ),
                {
                    "rowid": rowid,
                    "embedding": json.dumps(vector),
                    "vector_space": vector_space,
                    "vector_key": vector_key,
                    "photo_id": str(photo_id),
                },
            )

    async def delete(self, vector_key: str) -> None:
        rowid = _rowid_for(vector_key)
        async with self._writer.transaction() as connection:
            await connection.execute(
                text("DELETE FROM embedding_index WHERE rowid = :rowid"), {"rowid": rowid}
            )

    async def query(
        self, vector: Vector, *, vector_space: str, limit: int
    ) -> list[VectorSearchHit]:
        async with self._read_sessions() as session:
            result = await session.execute(
                text(
                    "SELECT photo_id, distance FROM embedding_index "
                    "WHERE embedding MATCH :embedding AND k = :k AND vector_space = :vector_space "
                    "ORDER BY distance"
                ),
                {"embedding": json.dumps(vector), "k": limit, "vector_space": vector_space},
            )
            return [
                VectorSearchHit(photo_id=uuid.UUID(photo_id_str), score=1.0 - distance)
                for photo_id_str, distance in result.all()
            ]


def _rowid_for(vector_key: str) -> int:
    digest = hashlib.sha256(vector_key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF
