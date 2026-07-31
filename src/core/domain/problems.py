from pydantic import BaseModel

from core.domain.library import PhotoId


class ProblemItem(BaseModel):
    photo_id: PhotoId
    error_message: str


class ProblemGroup(BaseModel):
    error_code: str
    items: list[ProblemItem]


class ProblemListResponse(BaseModel):
    groups: list[ProblemGroup]


class RetryProblemsRequest(BaseModel):
    photo_ids: list[PhotoId]


class IgnoreProblemsRequest(BaseModel):
    photo_ids: list[PhotoId]


class RetryProblemsResponse(BaseModel):
    job_id: str
