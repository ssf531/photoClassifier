import uuid
from collections.abc import Sequence

from core.domain.collections import CollectionSummary
from core.infrastructure.collection_repository import CollectionItemRepository, CollectionRepository
from core.infrastructure.db.collection_models import Collection


class UnknownCollectionError(Exception):
    pass


class CollectionManager:
    """`CollectionManager.create()`/`add_members()` (SDD §4.8): virtual
    collections have manual membership, and adding members is purely a DB
    write -- it never touches a photo's file on disk.
    """

    def __init__(
        self, collection_repo: CollectionRepository, item_repo: CollectionItemRepository
    ) -> None:
        self._collections = collection_repo
        self._items = item_repo

    async def create(self, name: str) -> Collection:
        return await self._collections.create(Collection(name=name, type="virtual"))

    async def list_collections(self) -> list[CollectionSummary]:
        collections = await self._collections.list(limit=500, offset=0)
        summaries = []
        for collection in collections:
            item_count = await self._items.count_by_collection(collection.id)
            summaries.append(
                CollectionSummary(
                    id=collection.id,
                    name=collection.name,
                    type=collection.type,
                    created_at=collection.created_at,
                    item_count=item_count,
                )
            )
        return summaries

    async def add_members(self, collection_id: uuid.UUID, photo_ids: Sequence[uuid.UUID]) -> None:
        collection = await self._collections.get(collection_id)
        if collection is None:
            raise UnknownCollectionError(collection_id)
        await self._items.bulk_add(collection_id, photo_ids)

    async def list_members(
        self, collection_id: uuid.UUID, *, limit: int, offset: int
    ) -> list[uuid.UUID]:
        collection = await self._collections.get(collection_id)
        if collection is None:
            raise UnknownCollectionError(collection_id)
        items = await self._items.list_by_collection(collection_id, limit=limit, offset=offset)
        return [item.photo_id for item in items]
