from sqlalchemy import text

from core.domain.search import EmbeddingService
from core.infrastructure.ai_result_repository import EmbeddingRefRepository
from core.infrastructure.db.write_connection import WriteConnection

_PAGE_SIZE = 200


async def rebuild_fts_index(writer: WriteConnection) -> None:
    """Rebuild every FTS5 shadow table from its current source-of-truth rows
    (SDD §7.3): recovery after corruption or an index-format upgrade,
    exactly the property "the index is derived and rebuildable" promises.
    One INSERT...SELECT per table -- no per-row Python loop needed, since
    the FTS5 tables' columns are a direct projection of their source table.
    """
    async with writer.transaction() as connection:
        await connection.execute(text("DELETE FROM ai_result_fts"))
        await connection.execute(text("DELETE FROM photo_fts"))
        await connection.execute(text("DELETE FROM metadata_fts"))

        await connection.execute(
            text(
                "INSERT INTO ai_result_fts(result_id, photo_id, capability, payload) "
                "SELECT id, photo_id, capability, payload FROM ai_result WHERE is_current = 1"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO photo_fts(photo_id, relative_path) SELECT id, relative_path FROM photo"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO metadata_fts(photo_id, camera_make, camera_model, lens) "
                "SELECT photo_id, camera_make, camera_model, lens FROM metadata"
            )
        )


async def rebuild_vector_index(
    embedding_refs: EmbeddingRefRepository, embedding_service: EmbeddingService
) -> None:
    """Rebuild the vector index by re-running the embedding provider for
    every photo `embedding_ref` records (SDD §7.3). Unlike FTS5, the vector
    index has no other durable copy of the raw embedding to project from --
    genuinely re-embedding is the only way to reconstruct it, so this is a
    deliberate, not-cheap maintenance action, not an instant rebuild.
    """
    offset = 0
    while True:
        page = await embedding_refs.list(limit=_PAGE_SIZE, offset=offset)
        for ref in page:
            await embedding_service.embed(ref.photo_id, ref.vector_space)
        if len(page) < _PAGE_SIZE:
            return
        offset += _PAGE_SIZE


async def full_reindex(
    writer: WriteConnection,
    embedding_refs: EmbeddingRefRepository,
    embedding_service: EmbeddingService,
) -> None:
    """Rebuild every derived search index from current source-of-truth rows
    (SDD §7.3): the maintenance action for recovery after corruption or an
    index-format upgrade."""
    await rebuild_fts_index(writer)
    await rebuild_vector_index(embedding_refs, embedding_service)
