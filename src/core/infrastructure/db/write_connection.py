import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine


class WriteConnection:
    """One write connection on the event loop, serialized by a lock.

    Per SDD §5.5 / AI Development Guide §4.4: no write queue, actor, or
    future-resolution layer — WAL mode plus a single serialized connection is
    the entire discipline.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._lock = asyncio.Lock()
        self._connection: AsyncConnection | None = None

    async def _get_connection(self) -> AsyncConnection:
        if self._connection is None:
            self._connection = await self._engine.connect()
        return self._connection

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncConnection]:
        async with self._lock:
            connection = await self._get_connection()
            async with connection.begin():
                yield connection

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
