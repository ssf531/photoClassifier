import inspect
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from core.infrastructure.db.base import Base, HasId
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.repository import SqlAlchemyRepository
from core.infrastructure.db.write_connection import WriteConnection


class ScratchItem(HasId):
    __tablename__ = "scratch_item"

    value: Mapped[str] = mapped_column(String)


class ScratchItemRepository(SqlAlchemyRepository[ScratchItem]):
    model = ScratchItem


@pytest.fixture
async def repository(tmp_path: Path) -> AsyncIterator[ScratchItemRepository]:
    engine = create_engine(tmp_path / "repo.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    try:
        yield ScratchItemRepository(create_session_factory(engine), writer)
    finally:
        await writer.close()
        await engine.dispose()


async def test_create_then_get_round_trips(repository: ScratchItemRepository) -> None:
    created = await repository.create(ScratchItem(value="hello"))

    fetched = await repository.get(created.id)

    assert fetched is not None
    assert fetched.value == "hello"


async def test_get_missing_returns_none(repository: ScratchItemRepository) -> None:
    assert await repository.get(uuid.uuid4()) is None


async def test_list_is_paginated(repository: ScratchItemRepository) -> None:
    expected_values = {f"item-{i}" for i in range(5)}
    for value in expected_values:
        await repository.create(ScratchItem(value=value))

    page_one = await repository.list(limit=2, offset=0)
    page_two = await repository.list(limit=2, offset=2)
    page_three = await repository.list(limit=2, offset=4)

    assert [len(page_one), len(page_two), len(page_three)] == [2, 2, 1]
    seen_values = {item.value for item in [*page_one, *page_two, *page_three]}
    assert seen_values == expected_values


async def test_update_persists_change(repository: ScratchItemRepository) -> None:
    created = await repository.create(ScratchItem(value="before"))
    created.value = "after"

    updated = await repository.update(created)

    assert updated.value == "after"
    assert (await repository.get(created.id)).value == "after"  # type: ignore[union-attr]


async def test_delete_removes_entity(repository: ScratchItemRepository) -> None:
    created = await repository.create(ScratchItem(value="temp"))

    await repository.delete(created.id)

    assert await repository.get(created.id) is None


def test_list_requires_pagination_arguments() -> None:
    params = inspect.signature(SqlAlchemyRepository.list).parameters
    assert params["limit"].default is inspect.Parameter.empty
    assert params["offset"].default is inspect.Parameter.empty
