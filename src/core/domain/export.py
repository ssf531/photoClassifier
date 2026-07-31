from pydantic import BaseModel

from core.domain.library import PhotoId


class ExportXmpRequest(BaseModel):
    photo_ids: list[PhotoId]
    preset: str = "default"


class ExportCollectionXmpRequest(BaseModel):
    preset: str = "default"


class ExportResultItem(BaseModel):
    photo_id: PhotoId
    success: bool
    error: str | None = None


class ExportReport(BaseModel):
    items: list[ExportResultItem]
