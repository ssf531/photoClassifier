import os
import shutil
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.infrastructure.collection_manager import CollectionManager, UnknownCollectionError
from core.infrastructure.collection_repository import CollectionItemRepository, CollectionRepository
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository

_PHOTO_COUNT = 10_000
_SEED_BATCH_SIZE = 2000


async def _seed_photos(
    writer: WriteConnection, library_root_id: uuid.UUID, count: int
) -> list[uuid.UUID]:
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    photo_ids = [uuid.uuid4() for _ in range(count)]
    generated = 0
    while generated < count:
        batch_end = min(generated + _SEED_BATCH_SIZE, count)
        async with writer.transaction() as connection:
            session = AsyncSession(bind=connection, expire_on_commit=False)
            for index in range(generated, batch_end):
                session.add(
                    Photo(
                        id=photo_ids[index],
                        library_root_id=library_root_id,
                        relative_path=f"{index}.jpg",
                        relative_path_folded=f"{index}.jpg",
                        size_bytes=1,
                        file_mtime=now,
                        status="active",
                    )
                )
            await session.flush()
        generated = batch_end
    return photo_ids


class _Env:
    def __init__(self, manager: CollectionManager, photo_ids: list[uuid.UUID]) -> None:
        self.manager = manager
        self.photo_ids = photo_ids


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "collections.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    library_root_repo = LibraryRootRepository(sessions, writer)
    root = await library_root_repo.create(LibraryRoot(path="/library"))
    photo_ids = await _seed_photos(writer, root.id, _PHOTO_COUNT)

    manager = CollectionManager(
        CollectionRepository(sessions, writer), CollectionItemRepository(sessions, writer)
    )

    try:
        yield _Env(manager, photo_ids)
    finally:
        await writer.close()
        await engine.dispose()


async def test_create_returns_a_virtual_collection(env: _Env) -> None:
    collection = await env.manager.create("Trip")

    assert collection.name == "Trip"
    assert collection.type == "virtual"


async def test_add_members_to_unknown_collection_raises(env: _Env) -> None:
    with pytest.raises(UnknownCollectionError):
        await env.manager.add_members(uuid.uuid4(), env.photo_ids[:1])


async def test_list_members_of_unknown_collection_raises(env: _Env) -> None:
    with pytest.raises(UnknownCollectionError):
        await env.manager.list_members(uuid.uuid4(), limit=10, offset=0)


async def test_add_members_then_list_members(env: _Env) -> None:
    collection = await env.manager.create("Trip")

    await env.manager.add_members(collection.id, env.photo_ids[:2])

    members = await env.manager.list_members(collection.id, limit=10, offset=0)
    assert set(members) == set(env.photo_ids[:2])


async def test_list_collections_reports_item_counts(env: _Env) -> None:
    collection = await env.manager.create("Trip")
    await env.manager.add_members(collection.id, env.photo_ids[:3])

    summaries = await env.manager.list_collections()

    assert len(summaries) == 1
    assert summaries[0].item_count == 3


async def test_adding_10000_photos_performs_zero_filesystem_writes(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FEAT-071's acceptance criterion (SDD §4.8: "membership never implies
    file movement"): adding photos to a collection is a pure DB write.
    Patch every filesystem-mutating primitive a careless implementation
    could reach for and assert `add_members()` never calls any of them --
    it doesn't touch a single photo's file on disk, no matter how many
    photos are added.
    """
    collection = await env.manager.create("Big trip")
    assert len(env.photo_ids) == _PHOTO_COUNT

    calls: list[str] = []

    def _record(name: str):
        def _fail(*_args: object, **_kwargs: object) -> None:
            calls.append(name)
            raise AssertionError(f"unexpected filesystem write via {name}")

        return _fail

    monkeypatch.setattr(shutil, "copy", _record("shutil.copy"))
    monkeypatch.setattr(shutil, "copy2", _record("shutil.copy2"))
    monkeypatch.setattr(shutil, "move", _record("shutil.move"))
    monkeypatch.setattr(Path, "write_bytes", _record("Path.write_bytes"))
    monkeypatch.setattr(Path, "write_text", _record("Path.write_text"))
    monkeypatch.setattr(Path, "unlink", _record("Path.unlink"))
    monkeypatch.setattr(os, "rename", _record("os.rename"))
    monkeypatch.setattr(os, "replace", _record("os.replace"))
    monkeypatch.setattr(os, "remove", _record("os.remove"))

    await env.manager.add_members(collection.id, env.photo_ids)

    assert calls == []
    assert len(await env.manager.list_members(collection.id, limit=_PHOTO_COUNT, offset=0)) == (
        _PHOTO_COUNT
    )
