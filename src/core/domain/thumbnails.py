from enum import Enum


class ThumbSize(str, Enum):  # noqa: UP042 -- kept pre-StrEnum pending broader migration
    GRID = "grid"
    PREVIEW = "preview"
