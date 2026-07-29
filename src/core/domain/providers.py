from dataclasses import dataclass
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
