from dataclasses import dataclass
from typing import Protocol

from core.domain.library import PhotoId
from core.domain.providers import Vector


@dataclass(frozen=True)
class TextSearchHit:
    photo_id: PhotoId
    score: float  # higher is more relevant


class TextSearchIndex(Protocol):
    async def search(self, query: str, *, limit: int, offset: int = 0) -> list[TextSearchHit]: ...


@dataclass(frozen=True)
class VectorSearchHit:
    photo_id: PhotoId
    score: float  # 1 - cosine distance; higher is more similar


class EmbeddingIndex(Protocol):
    """Vector similarity search (ADR-0003): application code depends on this
    interface, never on `sqlite-vec` directly, so a future higher-scale
    backend (e.g. LanceDB, TD-01) is a swap behind this seam."""

    async def upsert(
        self, *, vector_key: str, vector_space: str, photo_id: PhotoId, vector: Vector
    ) -> None: ...
    async def delete(self, vector_key: str) -> None: ...
    async def query(
        self, vector: Vector, *, vector_space: str, limit: int
    ) -> list[VectorSearchHit]: ...
