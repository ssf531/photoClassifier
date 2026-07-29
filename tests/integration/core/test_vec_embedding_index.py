import asyncio
import uuid
from argparse import Namespace
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.vec_embedding_index import SqliteVecEmbeddingIndex

REPO_ROOT = Path(__file__).resolve().parents[3]


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.cmd_opts = Namespace(x=[f"db_path={db_path}"])
    return cfg


@pytest.fixture
async def index(tmp_path: Path) -> AsyncIterator[SqliteVecEmbeddingIndex]:
    db_path = tmp_path / "vec_index.db"
    await asyncio.to_thread(command.upgrade, _alembic_config(db_path), "head")

    engine = create_engine(db_path)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    try:
        yield SqliteVecEmbeddingIndex(sessions, writer)
    finally:
        await writer.close()
        await engine.dispose()


def _vector(*, dims: int = 512, hot_index: int = 0) -> list[float]:
    vector = [0.0] * dims
    vector[hot_index] = 1.0
    return vector


async def test_query_finds_an_exact_match_with_score_near_one(
    index: SqliteVecEmbeddingIndex,
) -> None:
    photo_id = uuid.uuid4()
    await index.upsert(
        vector_key=f"{photo_id}:clip", vector_space="clip", photo_id=photo_id, vector=_vector()
    )

    hits = await index.query(_vector(), vector_space="clip", limit=5)

    assert len(hits) == 1
    assert hits[0].photo_id == photo_id
    assert hits[0].score == pytest.approx(1.0, abs=1e-6)


async def test_query_ranks_closer_vectors_above_orthogonal_ones(
    index: SqliteVecEmbeddingIndex,
) -> None:
    close_photo, far_photo, orthogonal_photo = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    close_vector = _vector()
    close_vector[1] = 0.05  # nearly identical direction to the query
    await index.upsert(
        vector_key=f"{close_photo}:clip",
        vector_space="clip",
        photo_id=close_photo,
        vector=close_vector,
    )
    await index.upsert(
        vector_key=f"{orthogonal_photo}:clip",
        vector_space="clip",
        photo_id=orthogonal_photo,
        vector=_vector(hot_index=1),
    )
    opposite_vector = [-v for v in _vector()]
    await index.upsert(
        vector_key=f"{far_photo}:clip",
        vector_space="clip",
        photo_id=far_photo,
        vector=opposite_vector,
    )

    hits = await index.query(_vector(), vector_space="clip", limit=10)

    assert [hit.photo_id for hit in hits] == [close_photo, orthogonal_photo, far_photo]
    assert hits[0].score > hits[1].score > hits[2].score


async def test_query_filters_by_vector_space(index: SqliteVecEmbeddingIndex) -> None:
    clip_photo, other_photo = uuid.uuid4(), uuid.uuid4()
    await index.upsert(
        vector_key=f"{clip_photo}:clip", vector_space="clip", photo_id=clip_photo, vector=_vector()
    )
    await index.upsert(
        vector_key=f"{other_photo}:other",
        vector_space="other-space",
        photo_id=other_photo,
        vector=_vector(),
    )

    hits = await index.query(_vector(), vector_space="clip", limit=10)

    assert [hit.photo_id for hit in hits] == [clip_photo]


async def test_reupserting_the_same_key_replaces_rather_than_duplicates(
    index: SqliteVecEmbeddingIndex,
) -> None:
    photo_id = uuid.uuid4()
    key = f"{photo_id}:clip"
    await index.upsert(vector_key=key, vector_space="clip", photo_id=photo_id, vector=_vector())

    await index.upsert(
        vector_key=key, vector_space="clip", photo_id=photo_id, vector=_vector(hot_index=1)
    )

    hits = await index.query(_vector(hot_index=1), vector_space="clip", limit=10)
    assert len(hits) == 1
    assert hits[0].score == pytest.approx(1.0, abs=1e-6)


async def test_delete_removes_the_vector(index: SqliteVecEmbeddingIndex) -> None:
    photo_id = uuid.uuid4()
    key = f"{photo_id}:clip"
    await index.upsert(vector_key=key, vector_space="clip", photo_id=photo_id, vector=_vector())

    await index.delete(key)

    hits = await index.query(_vector(), vector_space="clip", limit=10)
    assert hits == []
