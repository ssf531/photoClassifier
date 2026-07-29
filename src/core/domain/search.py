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
    async def get(self, vector_key: str) -> Vector | None: ...
    async def query(
        self, vector: Vector, *, vector_space: str, limit: int
    ) -> list[VectorSearchHit]: ...


@dataclass(frozen=True)
class ScoredPhoto:
    photo_id: PhotoId
    score: float


class EmbeddingService(Protocol):
    """Thin wrapper for embedding generation + storage/query (SDD §4.5),
    kept separate from the general Analysis Pipeline because embeddings have
    a distinct query pattern (ANN similarity) from other AI results."""

    async def embed(self, photo_id: PhotoId, provider: str) -> None: ...
    async def similar_to(self, photo_id: PhotoId, k: int) -> list[ScoredPhoto]: ...
    async def embed_text(self, query: str, provider: str) -> Vector: ...
