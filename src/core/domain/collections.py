import uuid
from datetime import datetime

from pydantic import BaseModel

from core.domain.library import PhotoId
from core.domain.search import SearchQueryRequest

CollectionId = uuid.UUID


class CollectionCreateRequest(BaseModel):
    name: str
    # A smart collection (SDD §4.8) is a saved SearchQuery evaluated live on
    # every read rather than a fixed membership list; omitted for a
    # virtual collection.
    search_query: SearchQueryRequest | None = None


class CollectionSummary(BaseModel):
    id: CollectionId
    name: str
    type: str
    created_at: datetime
    item_count: int


class CollectionListResponse(BaseModel):
    items: list[CollectionSummary]


class AddCollectionMembersRequest(BaseModel):
    photo_ids: list[PhotoId]


class CollectionMembersResponse(BaseModel):
    photo_ids: list[PhotoId]
    next_offset: int | None
