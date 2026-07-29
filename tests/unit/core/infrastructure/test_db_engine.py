from pathlib import Path

from sqlalchemy import text

from core.infrastructure.db.engine import create_engine, create_session_factory


async def test_engine_loads_sqlite_vec_extension(tmp_path: Path) -> None:
    engine = create_engine(tmp_path / "test.db")
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("select vec_version()"))
            assert result.scalar() is not None
    finally:
        await engine.dispose()


async def test_engine_enables_wal_mode(tmp_path: Path) -> None:
    engine = create_engine(tmp_path / "test.db")
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("PRAGMA journal_mode"))
            assert result.scalar() == "wal"
    finally:
        await engine.dispose()


async def test_session_factory_can_execute_a_query(tmp_path: Path) -> None:
    engine = create_engine(tmp_path / "test.db")
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            result = await session.execute(text("select 1"))
            assert result.scalar() == 1
    finally:
        await engine.dispose()
