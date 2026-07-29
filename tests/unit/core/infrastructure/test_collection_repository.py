import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from core.infrastructure.collection_repository import (
    CollectionItemRepository,
    CollectionRepository,
    SmartCollectionRuleRepository,
    UserDataRepository,
)
from core.infrastructure.db.base import Base
from core.infrastructure.db.collection_models import (
    Collection,
    CollectionItem,
    SmartCollectionRule,
    UserData,
)
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository


class _Env:
    def __init__(
        self,
        user_data: UserDataRepository,
        collections: CollectionRepository,
        rules: SmartCollectionRuleRepository,
        items: CollectionItemRepository,
        photo_id: uuid.UUID,
        other_photo_id: uuid.UUID,
    ) -> None:
        self.user_data = user_data
        self.collections = collections
        self.rules = rules
        self.items = items
        self.photo_id = photo_id
        self.other_photo_id = other_photo_id


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "collections.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    photo_repo = PhotoRepository(sessions, writer)
    library_root_repo = LibraryRootRepository(sessions, writer)
    root = await library_root_repo.create(LibraryRoot(path="/library"))
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    photo = await photo_repo.create(
        Photo(
            library_root_id=root.id,
            relative_path="a.jpg",
            relative_path_folded="a.jpg",
            size_bytes=1,
            file_mtime=now,
            status="active",
        )
    )
    other_photo = await photo_repo.create(
        Photo(
            library_root_id=root.id,
            relative_path="b.jpg",
            relative_path_folded="b.jpg",
            size_bytes=1,
            file_mtime=now,
            status="active",
        )
    )

    try:
        yield _Env(
            UserDataRepository(sessions, writer),
            CollectionRepository(sessions, writer),
            SmartCollectionRuleRepository(sessions, writer),
            CollectionItemRepository(sessions, writer),
            photo.id,
            other_photo.id,
        )
    finally:
        await writer.close()
        await engine.dispose()


async def test_user_data_get_returns_none_when_absent(env: _Env) -> None:
    assert await env.user_data.get_by_photo_id(env.photo_id) is None


async def test_user_data_upsert_creates_then_updates(env: _Env) -> None:
    await env.user_data.upsert(UserData(photo_id=env.photo_id, rating=3, favourite=False))
    updated = await env.user_data.upsert(UserData(photo_id=env.photo_id, rating=5, favourite=True))

    assert updated.rating == 5
    assert updated.favourite is True
    fetched = await env.user_data.get_by_photo_id(env.photo_id)
    assert fetched is not None
    assert fetched.rating == 5


async def test_user_data_rejects_unknown_photo_id(env: _Env) -> None:
    with pytest.raises(IntegrityError):
        await env.user_data.upsert(UserData(photo_id=uuid.uuid4(), favourite=False))


async def test_collection_create_and_list(env: _Env) -> None:
    await env.collections.create(Collection(name="Trip", type="virtual"))

    collections = await env.collections.list(limit=10, offset=0)
    assert [c.name for c in collections] == ["Trip"]


async def test_smart_collection_rule_upsert(env: _Env) -> None:
    collection = await env.collections.create(Collection(name="Recent", type="smart"))

    await env.rules.upsert(
        SmartCollectionRule(collection_id=collection.id, search_query={"text": "dog"})
    )
    updated = await env.rules.upsert(
        SmartCollectionRule(collection_id=collection.id, search_query={"text": "cat"})
    )

    assert updated.search_query == {"text": "cat"}


async def test_smart_collection_rule_rejects_unknown_collection(env: _Env) -> None:
    with pytest.raises(IntegrityError):
        await env.rules.upsert(SmartCollectionRule(collection_id=uuid.uuid4(), search_query={}))


async def test_collection_item_create_and_list_by_collection(env: _Env) -> None:
    collection = await env.collections.create(Collection(name="Trip", type="virtual"))
    await env.items.create(CollectionItem(collection_id=collection.id, photo_id=env.photo_id))
    await env.items.create(CollectionItem(collection_id=collection.id, photo_id=env.other_photo_id))

    members = await env.items.list_by_collection(collection.id)
    assert {m.photo_id for m in members} == {env.photo_id, env.other_photo_id}


async def test_collection_item_rejects_duplicate_membership(env: _Env) -> None:
    collection = await env.collections.create(Collection(name="Trip", type="virtual"))
    await env.items.create(CollectionItem(collection_id=collection.id, photo_id=env.photo_id))

    with pytest.raises(IntegrityError):
        await env.items.create(CollectionItem(collection_id=collection.id, photo_id=env.photo_id))
