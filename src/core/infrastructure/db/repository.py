from typing import Any, Generic, Protocol, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.infrastructure.db.base import HasId
from core.infrastructure.db.write_connection import WriteConnection

T = TypeVar("T", bound=HasId)


class Repository(Protocol[T]):
    async def get(self, entity_id: Any) -> T | None: ...

    async def list(self, *, limit: int, offset: int) -> list[T]: ...

    async def create(self, entity: T) -> T: ...

    async def update(self, entity: T) -> T: ...

    async def delete(self, entity_id: Any) -> None: ...


class SqlAlchemyRepository(Generic[T]):  # noqa: UP046 -- kept pre-PEP-695 pending broader migration
    model: type[T]

    def __init__(
        self, read_sessions: async_sessionmaker[AsyncSession], writer: WriteConnection
    ) -> None:
        self._read_sessions = read_sessions
        self._writer = writer

    async def get(self, entity_id: Any) -> T | None:
        async with self._read_sessions() as session:
            return await session.get(self.model, entity_id)

    async def list(self, *, limit: int, offset: int) -> list[T]:
        async with self._read_sessions() as session:
            result = await session.execute(
                select(self.model).order_by(self.model.id).limit(limit).offset(offset)
            )
            return list(result.scalars().all())

    async def create(self, entity: T) -> T:
        async with self._writer.transaction() as connection:
            session = AsyncSession(bind=connection, expire_on_commit=False)
            session.add(entity)
            await session.flush()
            await session.refresh(entity)
            return entity

    async def update(self, entity: T) -> T:
        async with self._writer.transaction() as connection:
            session = AsyncSession(bind=connection, expire_on_commit=False)
            merged = await session.merge(entity)
            await session.flush()
            await session.refresh(merged)
            return merged

    async def delete(self, entity_id: Any) -> None:
        async with self._writer.transaction() as connection:
            session = AsyncSession(bind=connection, expire_on_commit=False)
            obj = await session.get(self.model, entity_id)
            if obj is not None:
                await session.delete(obj)
                await session.flush()
