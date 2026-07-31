import asyncio
import os
import shutil
import uuid
from argparse import Namespace
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from core.domain.providers import Vector
from core.domain.search import ScoredPhoto, SearchQueryRequest
from core.infrastructure.collection_manager import CollectionManager, UnknownCollectionError
from core.infrastructure.collection_repository import (
    CollectionItemRepository,
    CollectionRepository,
    SmartCollectionRuleRepository,
)
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.fts_search_index import FtsTextSearchIndex
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.search_service import DefaultSearchService
from core.infrastructure.vec_embedding_index import SqliteVecEmbeddingIndex

REPO_ROOT = Path(__file__).resolve().parents[4]


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.cmd_opts = Namespace(x=[f"db_path={db_path}"])
    return cfg


class _UnusedEmbeddingService:
    """`DefaultSearchService` requires an `EmbeddingService`, but every test
    here only exercises `text`/`metadata` search modes, which never call it.
    """

    async def embed(self, photo_id: uuid.UUID, provider: str) -> None:
        raise NotImplementedError

    async def similar_to(self, photo_id: uuid.UUID, k: int) -> list[ScoredPhoto]:
        raise NotImplementedError

    async def embed_text(self, query: str, provider: str) -> Vector:
        raise NotImplementedError


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
    def __init__(
        self,
        manager: CollectionManager,
        photo_ids: list[uuid.UUID],
        photo_repo: PhotoRepository,
        library_root_id: uuid.UUID,
    ) -> None:
        self.manager = manager
        self.photo_ids = photo_ids
        self.photo_repo = photo_repo
        self.library_root_id = library_root_id

    async def add_photo(self, relative_path: str) -> uuid.UUID:
        now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
        photo = await self.photo_repo.create(
            Photo(
                library_root_id=self.library_root_id,
                relative_path=relative_path,
                relative_path_folded=relative_path.lower(),
                size_bytes=1,
                file_mtime=now,
                status="active",
            )
        )
        return photo.id


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    db_path = tmp_path / "collections.db"
    await asyncio.to_thread(command.upgrade, _alembic_config(db_path), "head")

    engine = create_engine(db_path)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    library_root_repo = LibraryRootRepository(sessions, writer)
    photo_repo = PhotoRepository(sessions, writer)
    root = await library_root_repo.create(LibraryRoot(path="/library"))
    photo_ids = await _seed_photos(writer, root.id, _PHOTO_COUNT)

    search_service = DefaultSearchService(
        text_index=FtsTextSearchIndex(sessions),
        embedding_index=SqliteVecEmbeddingIndex(sessions, writer),
        embedding_service=_UnusedEmbeddingService(),
        read_sessions=sessions,
        default_embedding_provider="clip",
    )
    manager = CollectionManager(
        CollectionRepository(sessions, writer),
        CollectionItemRepository(sessions, writer),
        SmartCollectionRuleRepository(sessions, writer),
        search_service,
    )

    try:
        yield _Env(manager, photo_ids, photo_repo, root.id)
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


async def test_list_all_members_pages_through_every_member(env: _Env) -> None:
    """`list_all_members()` (TASK-084) internally pages past a single
    `list_members()` call's page size so a caller (e.g. batch-exporting an
    entire collection) gets every member back in one call.
    """
    collection = await env.manager.create("Big trip")
    target = env.photo_ids[:1200]
    await env.manager.add_members(collection.id, target)

    members = await env.manager.list_all_members(collection.id)

    assert set(members) == set(target)
    assert len(members) == len(target)


async def test_list_all_members_of_unknown_collection_raises(env: _Env) -> None:
    with pytest.raises(UnknownCollectionError):
        await env.manager.list_all_members(uuid.uuid4())


async def test_create_smart_returns_a_smart_collection(env: _Env) -> None:
    collection = await env.manager.create_smart(
        "Sunsets", SearchQueryRequest(text="sunset", mode="text")
    )

    assert collection.name == "Sunsets"
    assert collection.type == "smart"


async def test_evaluate_smart_returns_photos_matching_the_saved_query(env: _Env) -> None:
    matching_id = await env.add_photo("sunset-beach.jpg")
    await env.add_photo("receipt-scan.jpg")
    collection = await env.manager.create_smart(
        "Sunsets", SearchQueryRequest(text="sunset", mode="text")
    )

    members = await env.manager.list_members(collection.id, limit=10, offset=0)

    assert members == [matching_id]


async def test_evaluate_smart_reflects_a_newly_indexed_matching_photo_without_refresh(
    env: _Env,
) -> None:
    """FEAT-072's acceptance criterion: a smart collection's membership
    updates immediately after a new matching photo is indexed, with no
    manual refresh action -- because it's evaluated live, not cached.
    """
    collection = await env.manager.create_smart(
        "Sunsets", SearchQueryRequest(text="sunset", mode="text")
    )
    assert await env.manager.list_members(collection.id, limit=10, offset=0) == []

    new_photo_id = await env.add_photo("sunset-cliff.jpg")

    members = await env.manager.list_members(collection.id, limit=10, offset=0)
    assert members == [new_photo_id]


async def test_evaluate_smart_of_unknown_collection_raises(env: _Env) -> None:
    with pytest.raises(UnknownCollectionError):
        await env.manager.evaluate_smart(uuid.uuid4(), limit=10, offset=0)


async def test_list_collections_reports_a_live_item_count_for_smart_collections(
    env: _Env,
) -> None:
    await env.add_photo("sunset-1.jpg")
    await env.add_photo("sunset-2.jpg")
    await env.manager.create_smart("Sunsets", SearchQueryRequest(text="sunset", mode="text"))

    summaries = await env.manager.list_collections()

    assert len(summaries) == 1
    assert summaries[0].type == "smart"
    assert summaries[0].item_count == 2
