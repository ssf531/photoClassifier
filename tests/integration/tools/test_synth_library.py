from pathlib import Path

from sqlalchemy import func, select, text

from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import Photo
from core.infrastructure.db.metadata_models import Metadata
from tools.synth_library import generate

_COUNT = 500


async def test_generate_produces_the_requested_row_count_with_a_healthy_db(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "synthetic.db"

    await generate(db_path, _COUNT, seed=42)

    engine = create_engine(db_path)
    sessions = create_session_factory(engine)
    async with sessions() as session:
        photo_count = (await session.execute(select(func.count()).select_from(Photo))).scalar_one()
        metadata_count = (
            await session.execute(select(func.count()).select_from(Metadata))
        ).scalar_one()
        integrity = (await session.execute(text("PRAGMA integrity_check"))).scalar_one()

        sample = (await session.execute(select(Photo).limit(1))).scalar_one()

    await engine.dispose()  # type: ignore[attr-defined]

    assert photo_count == _COUNT
    assert metadata_count == _COUNT
    assert integrity == "ok"
    assert sample.content_hash is not None
    assert len(sample.content_hash) == 16  # xxh3_64 hex digest


async def test_generate_is_deterministic_for_a_given_seed(tmp_path: Path) -> None:
    first_db = tmp_path / "first.db"
    second_db = tmp_path / "second.db"

    await generate(first_db, 50, seed=7)
    await generate(second_db, 50, seed=7)

    first_engine = create_engine(first_db)
    second_engine = create_engine(second_db)
    first_sessions = create_session_factory(first_engine)
    second_sessions = create_session_factory(second_engine)

    async with first_sessions() as session:
        first_hashes = (
            (await session.execute(select(Photo.content_hash).order_by(Photo.relative_path)))
            .scalars()
            .all()
        )
    async with second_sessions() as session:
        second_hashes = (
            (await session.execute(select(Photo.content_hash).order_by(Photo.relative_path)))
            .scalars()
            .all()
        )

    await first_engine.dispose()  # type: ignore[attr-defined]
    await second_engine.dispose()  # type: ignore[attr-defined]

    assert first_hashes == second_hashes
