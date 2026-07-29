import asyncio
from pathlib import Path

from sqlalchemy import text

from core.infrastructure.db.engine import create_engine
from core.infrastructure.db.write_connection import WriteConnection

WRITER_COUNT = 50
READER_COUNT = 50


async def test_fifty_writers_and_fifty_readers_no_busy_errors_no_lost_writes(
    tmp_path: Path,
) -> None:
    engine = create_engine(tmp_path / "concurrency.db")
    writer = WriteConnection(engine)
    try:
        async with writer.transaction() as conn:
            await conn.execute(text("CREATE TABLE scratch (id INTEGER PRIMARY KEY, value TEXT)"))

        async def write_one(i: int) -> None:
            async with writer.transaction() as conn:
                await conn.execute(
                    text("INSERT INTO scratch (value) VALUES (:value)"), {"value": f"row-{i}"}
                )

        async def read_count() -> int:
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT COUNT(*) FROM scratch"))
                return result.scalar_one()

        writers = [write_one(i) for i in range(WRITER_COUNT)]
        readers = [read_count() for _ in range(READER_COUNT)]
        await asyncio.gather(*writers, *readers)

        async with engine.connect() as conn:
            final_count = (await conn.execute(text("SELECT COUNT(*) FROM scratch"))).scalar_one()
            distinct_values = (
                await conn.execute(text("SELECT COUNT(DISTINCT value) FROM scratch"))
            ).scalar_one()

        assert final_count == WRITER_COUNT
        assert distinct_values == WRITER_COUNT
    finally:
        await writer.close()
        await engine.dispose()
