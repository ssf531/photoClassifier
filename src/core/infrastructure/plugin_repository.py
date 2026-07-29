from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.infrastructure.db.plugin_models import Plugin
from core.infrastructure.db.write_connection import WriteConnection


class PluginRepository:
    """Persists the `plugin` table's enabled/disabled state (SDD §4.7, ERD).

    Plugins are keyed by their manifest-declared string id, not a generated
    UUID, so this repository does not use the generic `SqlAlchemyRepository`.
    """

    def __init__(
        self, read_sessions: async_sessionmaker[AsyncSession], writer: WriteConnection
    ) -> None:
        self._read_sessions = read_sessions
        self._writer = writer

    async def get(self, plugin_id: str) -> Plugin | None:
        async with self._read_sessions() as session:
            return await session.get(Plugin, plugin_id)

    async def list_enabled(self) -> list[Plugin]:
        """Not paginated: bounded by installed-plugin count, which is a manifest-
        discovery-time quantity, not a photo-library-scale one (Guide §4.5)."""
        async with self._read_sessions() as session:
            result = await session.execute(
                select(Plugin).where(Plugin.enabled.is_(True)).order_by(Plugin.id)
            )
            return list(result.scalars().all())

    async def list(self, *, limit: int, offset: int) -> list[Plugin]:
        async with self._read_sessions() as session:
            result = await session.execute(
                select(Plugin).order_by(Plugin.id).limit(limit).offset(offset)
            )
            return list(result.scalars().all())

    async def upsert(self, plugin: Plugin) -> Plugin:
        async with self._writer.transaction() as connection:
            session = AsyncSession(bind=connection, expire_on_commit=False)
            merged = await session.merge(plugin)
            await session.flush()
            await session.refresh(merged)
            return merged
