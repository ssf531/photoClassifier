from pydantic import BaseModel

from core.domain.library import PhotoId


class ExportXmpRequest(BaseModel):
    photo_ids: list[PhotoId]


class ExportResultItem(BaseModel):
    photo_id: PhotoId
    success: bool
    error: str | None = None


class ExportReport(BaseModel):
    items: list[ExportResultItem]
