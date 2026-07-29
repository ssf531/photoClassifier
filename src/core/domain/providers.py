from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from core.domain.library import PhotoId


@dataclass(frozen=True)
class ImageRef:
    """What a capability provider needs to read a photo's pixels (SDD §6.1)."""

    photo_id: PhotoId
    path: Path


@dataclass(frozen=True)
class QualityResult:
    """Every `*Result` DTO carries `provider_id`/`model_version`/`confidence`/
    `raw_payload` so the Analysis Pipeline can persist it generically without
    knowing capability-specific shapes (SDD §6.1); quality-specific fields
    (sharpness, exposure) live in `raw_payload`.
    """

    provider_id: str
    model_version: str
    confidence: float
    raw_payload: dict[str, Any]


class QualityProvider(Protocol):
    async def assess(self, image: ImageRef) -> QualityResult: ...


@dataclass(frozen=True)
class DuplicateCandidate:
    """A photo as input to duplicate grouping: enough to hash its pixels and,
    for the members of a group, to recommend a keeper (SDD §10 -- highest
    resolution, then earliest capture time).
    """

    photo_id: PhotoId
    path: Path
    width: int
    height: int
    captured_at: datetime | None


@dataclass(frozen=True)
class DuplicateGroupMemberResult:
    photo_id: PhotoId
    similarity_score: float
    is_recommended_keeper: bool


@dataclass(frozen=True)
class DuplicateGroupResult:
    detection_method: str
    members: list[DuplicateGroupMemberResult]


Vector = list[float]


class EmbeddingProvider(Protocol):
    async def embed_image(self, image: ImageRef) -> Vector: ...
    async def embed_text(self, text: str) -> Vector: ...  # same space, for NL search
