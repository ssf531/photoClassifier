import uuid
from enum import Enum

PhotoId = uuid.UUID
LibraryRootId = uuid.UUID

RASTER_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"})
RAW_EXTENSIONS = frozenset({".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2"})
HEIC_EXTENSIONS = frozenset({".heic", ".heif"})
SUPPORTED_PHOTO_EXTENSIONS = RASTER_EXTENSIONS | RAW_EXTENSIONS | HEIC_EXTENSIONS


class FileStatus(str, Enum):  # noqa: UP042 -- kept pre-StrEnum pending broader migration
    ACTIVE = "active"
    MISSING = "missing"
    DELETED = "deleted"
