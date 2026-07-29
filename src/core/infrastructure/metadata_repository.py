import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.infrastructure.db.metadata_models import Metadata
from core.infrastructure.db.write_connection import WriteConnection


class MetadataRepository:
    """A 1:1 companion table to `photo`, keyed by `photo_id` itself -- not a
    generic paginated collection, so this does not extend SqlAlchemyRepository.
    """

    def __init__(
        self, read_sessions: async_sessionmaker[AsyncSession], writer: WriteConnection
    ) -> None:
        self._read_sessions = read_sessions
        self._writer = writer

    async def get_by_photo_id(self, photo_id: uuid.UUID) -> Metadata | None:
        async with self._read_sessions() as session:
            return await session.get(Metadata, photo_id)

    async def upsert(self, metadata: Metadata) -> Metadata:
        async with self._writer.transaction() as connection:
            session = AsyncSession(bind=connection, expire_on_commit=False)
            merged = await session.merge(metadata)
            await session.flush()
            await session.refresh(merged)
            return merged
