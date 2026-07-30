from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel

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


@dataclass(frozen=True)
class DateRange:
    start: datetime | None = None
    end: datetime | None = None


@dataclass(frozen=True)
class GpsBoundingBox:
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


@dataclass(frozen=True)
class MetadataFilters:
    """Hard filters (SDD §7.2): applied as SQL WHERE, intersected with any
    text/vector candidate set before ranking. `date_range` is against
    `captured_at_local` (ADR-0011) -- never a UTC column, per the timestamp
    policy."""

    date_range: DateRange | None = None
    camera_model: str | None = None
    min_rating: int | None = None
    gps_bbox: GpsBoundingBox | None = None


SearchMode = Literal["metadata", "text", "semantic", "hybrid", "similar_to"]


@dataclass(frozen=True)
class SearchQuery:
    """Unifies all search modes behind one contract (SDD §7.1)."""

    text: str | None = None
    filters: MetadataFilters | None = None
    mode: SearchMode = "hybrid"
    reference_photo_id: PhotoId | None = None
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True)
class SearchResult:
    photo_id: PhotoId
    score: float


@dataclass(frozen=True)
class SearchResults:
    results: list[SearchResult] = field(default_factory=list)


class SearchService(Protocol):
    # SDD §4.6 also lists index_photo(photo_id) for incremental index
    # maintenance; omitted here since its v1 semantics aren't decided yet
    # (FTS5 already syncs via triggers, and EmbeddingService.embed() already
    # handles embeddings directly) -- add it when TASK-059 needs it.
    async def search(self, query: SearchQuery) -> SearchResults: ...


# --- API-facing request/response models (TASK-067) -------------------------
# SearchQuery et al. above are the internal application contract (plain
# dataclasses); these Pydantic models are the wire format the UI's search
# bar actually sends, converted to/from the dataclasses at the API boundary.


class DateRangeRequest(BaseModel):
    start: datetime | None = None
    end: datetime | None = None


class GpsBoundingBoxRequest(BaseModel):
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


class MetadataFiltersRequest(BaseModel):
    date_range: DateRangeRequest | None = None
    camera_model: str | None = None
    min_rating: int | None = None
    gps_bbox: GpsBoundingBoxRequest | None = None


class SearchQueryRequest(BaseModel):
    text: str | None = None
    filters: MetadataFiltersRequest | None = None
    mode: SearchMode = "hybrid"
    reference_photo_id: PhotoId | None = None
    limit: int = 100
    offset: int = 0


class SearchResultItem(BaseModel):
    id: PhotoId
    relative_path: str
    captured_at_utc: datetime | None
    score: float


class SearchResponse(BaseModel):
    items: list[SearchResultItem]


def search_query_from_request(request: SearchQueryRequest) -> SearchQuery:
    filters = None
    if request.filters is not None:
        date_range = None
        if request.filters.date_range is not None:
            date_range = DateRange(
                start=request.filters.date_range.start, end=request.filters.date_range.end
            )
        gps_bbox = None
        if request.filters.gps_bbox is not None:
            gps_bbox = GpsBoundingBox(
                min_lat=request.filters.gps_bbox.min_lat,
                max_lat=request.filters.gps_bbox.max_lat,
                min_lon=request.filters.gps_bbox.min_lon,
                max_lon=request.filters.gps_bbox.max_lon,
            )
        filters = MetadataFilters(
            date_range=date_range,
            camera_model=request.filters.camera_model,
            min_rating=request.filters.min_rating,
            gps_bbox=gps_bbox,
        )

    return SearchQuery(
        text=request.text,
        filters=filters,
        mode=request.mode,
        reference_photo_id=request.reference_photo_id,
        limit=request.limit,
        offset=request.offset,
    )
