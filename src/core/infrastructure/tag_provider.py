import json
import math
from pathlib import Path

from core.domain.providers import ImageRef, TagResult, TagScore, Vector
from core.infrastructure.clip_embedding_provider import ClipEmbeddingProvider

PROVIDER_ID = "clip-zero-shot-tagging"
DEFAULT_VOCABULARY_PATH = Path(__file__).resolve().parent.parent / "tag_vocabulary_v1.json"

TOP_K = 5
# Empirically calibrated against this project's downloaded CLIP model: an
# unrelated label typically scores ~0.20-0.25 cosine similarity against a
# photo, a correct one clears ~0.26+ (SDD §6.1/ADR-0006). Raw CLIP cosine
# similarity is compressed and vocabulary-dependent, so this is a tunable
# starting point, not a universal constant -- revisit if tags feel noisy.
MIN_CONFIDENCE = 0.25


class TaggingProvider:
    """Zero-shot tagging derived from CLIP embeddings (ADR-0006): scores a
    photo's image embedding against a precomputed, versioned label
    vocabulary instead of using a second dedicated model. Reuses the CLIP
    provider's own availability -- there is no separate model to acquire.
    """

    provider_id = PROVIDER_ID

    def __init__(
        self,
        embedding_provider: ClipEmbeddingProvider,
        vocabulary_path: Path = DEFAULT_VOCABULARY_PATH,
        *,
        top_k: int = TOP_K,
        min_confidence: float = MIN_CONFIDENCE,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._top_k = top_k
        self._min_confidence = min_confidence

        vocabulary = json.loads(vocabulary_path.read_text(encoding="utf-8"))
        self._vocabulary_version: str = vocabulary["version"]
        self._labels: list[str] = vocabulary["labels"]
        self._label_embeddings: list[Vector] | None = None

    @property
    def model_version(self) -> str:
        return f"{self._embedding_provider.model_version}+{self._vocabulary_version}"

    def is_available(self) -> bool:
        return self._embedding_provider.is_available()

    async def tag(self, image: ImageRef) -> TagResult:
        await self._ensure_label_embeddings()
        assert self._label_embeddings is not None

        image_embedding = await self._embedding_provider.embed_image(image)
        scored = sorted(
            (
                (label, _cosine_similarity(image_embedding, label_embedding))
                for label, label_embedding in zip(self._labels, self._label_embeddings, strict=True)
            ),
            key=lambda item: item[1],
            reverse=True,
        )

        top_tags = [
            TagScore(label=label, confidence=score)
            for label, score in scored[: self._top_k]
            if score >= self._min_confidence
        ]

        return TagResult(
            provider_id=self.provider_id,
            model_version=self.model_version,
            confidence=top_tags[0].confidence if top_tags else 0.0,
            raw_payload={
                "tags": [{"label": t.label, "confidence": t.confidence} for t in top_tags]
            },
        )

    async def _ensure_label_embeddings(self) -> None:
        if self._label_embeddings is not None:
            return
        self._label_embeddings = [
            await self._embedding_provider.embed_text(f"a photo of {label}")
            for label in self._labels
        ]


def _cosine_similarity(a: Vector, b: Vector) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b)
