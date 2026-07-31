import uuid
from collections.abc import Sequence
from dataclasses import replace

from core.domain.collections import CollectionSummary
from core.domain.search import SearchQueryRequest, SearchService, search_query_from_request
from core.infrastructure.collection_repository import (
    CollectionItemRepository,
    CollectionRepository,
    SmartCollectionRuleRepository,
)
from core.infrastructure.db.collection_models import Collection, SmartCollectionRule

_SMART_COUNT_LIMIT = 1000


class UnknownCollectionError(Exception):
    pass


class CollectionManager:
    """`CollectionManager.create()`/`add_members()`/`evaluate_smart()` (SDD
    §4.8): a virtual collection has manual membership -- adding members is
    purely a DB write, it never touches a photo's file on disk -- while a
    smart collection is a saved `SearchQuery` evaluated live on every read,
    so a newly-indexed matching photo appears with no manual refresh.
    """

    def __init__(
        self,
        collection_repo: CollectionRepository,
        item_repo: CollectionItemRepository,
        rule_repo: SmartCollectionRuleRepository,
        search_service: SearchService,
    ) -> None:
        self._collections = collection_repo
        self._items = item_repo
        self._rules = rule_repo
        self._search_service = search_service

    async def create(self, name: str) -> Collection:
        return await self._collections.create(Collection(name=name, type="virtual"))

    async def create_smart(self, name: str, search_query: SearchQueryRequest) -> Collection:
        collection = await self._collections.create(Collection(name=name, type="smart"))
        await self._rules.upsert(
            SmartCollectionRule(
                collection_id=collection.id, search_query=search_query.model_dump(mode="json")
            )
        )
        return collection

    async def list_collections(self) -> list[CollectionSummary]:
        collections = await self._collections.list(limit=500, offset=0)
        summaries = []
        for collection in collections:
            if collection.type == "smart":
                item_count = len(
                    await self.evaluate_smart(collection.id, limit=_SMART_COUNT_LIMIT, offset=0)
                )
            else:
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
        if collection.type == "smart":
            return await self.evaluate_smart(collection_id, limit=limit, offset=offset)
        items = await self._items.list_by_collection(collection_id, limit=limit, offset=offset)
        return [item.photo_id for item in items]

    async def evaluate_smart(
        self, collection_id: uuid.UUID, *, limit: int, offset: int
    ) -> list[uuid.UUID]:
        rule = await self._rules.get_by_collection_id(collection_id)
        if rule is None:
            raise UnknownCollectionError(collection_id)
        saved_query = search_query_from_request(
            SearchQueryRequest.model_validate(rule.search_query)
        )
        results = await self._search_service.search(
            replace(saved_query, limit=limit, offset=offset)
        )
        return [result.photo_id for result in results.results]
