from pydantic import BaseModel

from core.domain.library import PhotoId


class CopyToFolderRequest(BaseModel):
    photo_ids: list[PhotoId]
    destination_folder: str


class CopyResultItem(BaseModel):
    photo_id: PhotoId
    success: bool
    destination_path: str | None = None
    error: str | None = None


class CopyReport(BaseModel):
    items: list[CopyResultItem]
