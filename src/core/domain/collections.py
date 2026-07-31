import uuid
from datetime import datetime

from pydantic import BaseModel

from core.domain.library import PhotoId

CollectionId = uuid.UUID


class CollectionCreateRequest(BaseModel):
    name: str


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
