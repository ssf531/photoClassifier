import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.infrastructure.db.collection_models import (
    Collection,
    CollectionItem,
    SmartCollectionRule,
    UserData,
)
from core.infrastructure.db.repository import SqlAlchemyRepository
from core.infrastructure.db.write_connection import WriteConnection

_BULK_ADD_BATCH_SIZE = 300


class UserDataRepository:
    """A 1:1 companion table to `photo`, keyed by `photo_id` itself -- not a
    generic paginated collection, so this does not extend SqlAlchemyRepository.
    """

    def __init__(
        self, read_sessions: async_sessionmaker[AsyncSession], writer: WriteConnection
    ) -> None:
        self._read_sessions = read_sessions
        self._writer = writer

    async def get_by_photo_id(self, photo_id: uuid.UUID) -> UserData | None:
        async with self._read_sessions() as session:
            return await session.get(UserData, photo_id)

    async def upsert(self, user_data: UserData) -> UserData:
        async with self._writer.transaction() as connection:
            session = AsyncSession(bind=connection, expire_on_commit=False)
            merged = await session.merge(user_data)
            await session.flush()
            await session.refresh(merged)
            return merged


class CollectionRepository(SqlAlchemyRepository[Collection]):
    model = Collection


class SmartCollectionRuleRepository:
    """A 1:1 companion table to `collection`, keyed by `collection_id` itself."""

    def __init__(
        self, read_sessions: async_sessionmaker[AsyncSession], writer: WriteConnection
    ) -> None:
        self._read_sessions = read_sessions
        self._writer = writer

    async def get_by_collection_id(self, collection_id: uuid.UUID) -> SmartCollectionRule | None:
        async with self._read_sessions() as session:
            return await session.get(SmartCollectionRule, collection_id)

    async def upsert(self, rule: SmartCollectionRule) -> SmartCollectionRule:
        async with self._writer.transaction() as connection:
            session = AsyncSession(bind=connection, expire_on_commit=False)
            merged = await session.merge(rule)
            await session.flush()
            await session.refresh(merged)
            return merged


class CollectionItemRepository(SqlAlchemyRepository[CollectionItem]):
    model = CollectionItem

    async def list_by_collection(
        self, collection_id: uuid.UUID, *, limit: int, offset: int
    ) -> list[CollectionItem]:
        async with self._read_sessions() as session:
            result = await session.execute(
                select(CollectionItem)
                .where(CollectionItem.collection_id == collection_id)
                .order_by(CollectionItem.id)
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    async def count_by_collection(self, collection_id: uuid.UUID) -> int:
        async with self._read_sessions() as session:
            result = await session.execute(
                select(func.count())
                .select_from(CollectionItem)
                .where(CollectionItem.collection_id == collection_id)
            )
            return result.scalar_one()

    async def bulk_add(self, collection_id: uuid.UUID, photo_ids: Sequence[uuid.UUID]) -> None:
        """Multi-row `INSERT ... ON CONFLICT DO NOTHING` batches, all in one
        transaction (SDD §4.8: "membership never implies file movement") --
        adding thousands of photos is a handful of DB writes, not one
        `create()` call per photo. Batched below SQLite's bound-parameter
        limit (3 columns/row; the oldest supported build caps at 999 total).
        """
        if not photo_ids:
            return
        async with self._writer.transaction() as connection:
            for start in range(0, len(photo_ids), _BULK_ADD_BATCH_SIZE):
                batch = photo_ids[start : start + _BULK_ADD_BATCH_SIZE]
                stmt = (
                    sqlite_insert(CollectionItem)
                    .values(
                        [
                            {
                                "id": uuid.uuid4(),
                                "collection_id": collection_id,
                                "photo_id": photo_id,
                            }
                            for photo_id in batch
                        ]
                    )
                    .on_conflict_do_nothing(index_elements=["collection_id", "photo_id"])
                )
                await connection.execute(stmt)
