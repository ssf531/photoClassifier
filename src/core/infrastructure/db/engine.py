from pathlib import Path
from typing import Any

import sqlite_vec
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


async def _load_extension_and_pragmas(aiosqlite_connection: Any) -> None:
    await aiosqlite_connection.enable_load_extension(True)
    await aiosqlite_connection.load_extension(sqlite_vec.loadable_path())
    await aiosqlite_connection.enable_load_extension(False)
    await aiosqlite_connection.execute("PRAGMA journal_mode=WAL")
    await aiosqlite_connection.execute("PRAGMA busy_timeout=5000")
    await aiosqlite_connection.execute("PRAGMA foreign_keys=ON")


def _on_connect(dbapi_connection: Any, connection_record: Any) -> None:
    dbapi_connection.run_async(_load_extension_and_pragmas)


def create_engine(db_path: Path) -> AsyncEngine:
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    event.listens_for(engine.sync_engine, "connect")(_on_connect)
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
