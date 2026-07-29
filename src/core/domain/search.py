from dataclasses import dataclass
from typing import Protocol

from core.domain.library import PhotoId


@dataclass(frozen=True)
class TextSearchHit:
    photo_id: PhotoId
    score: float  # higher is more relevant


class TextSearchIndex(Protocol):
    async def search(self, query: str, *, limit: int, offset: int = 0) -> list[TextSearchHit]: ...
