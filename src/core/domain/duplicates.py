import uuid
from datetime import datetime

from pydantic import BaseModel

from core.domain.library import PhotoId


class DuplicateGroupMemberSummary(BaseModel):
    photo_id: PhotoId
    similarity_score: float
    is_recommended_keeper: bool


class DuplicateGroupSummary(BaseModel):
    id: uuid.UUID
    detection_method: str
    created_at: datetime
    members: list[DuplicateGroupMemberSummary]


class DuplicateGroupListResponse(BaseModel):
    items: list[DuplicateGroupSummary]
    next_offset: int | None
