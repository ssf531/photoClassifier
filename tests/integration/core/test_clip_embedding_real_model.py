import asyncio
import math
import uuid
from pathlib import Path

import pytest

from core.domain.providers import ImageRef
from core.domain.settings import models_dir
from core.infrastructure.clip_embedding_provider import ClipEmbeddingProvider

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "clip"

pytestmark = pytest.mark.skipif(
    not ClipEmbeddingProvider(models_dir(), asyncio.Semaphore(1)).is_available(),
    reason="CLIP model not downloaded into the local model cache (TASK-0C acquisition path)",
)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b)


@pytest.fixture
def provider() -> ClipEmbeddingProvider:
    return ClipEmbeddingProvider(models_dir(), asyncio.Semaphore(1))


async def test_embedding_the_same_image_twice_is_deterministic(
    provider: ClipEmbeddingProvider,
) -> None:
    image = ImageRef(photo_id=uuid.uuid4(), path=FIXTURES_DIR / "red.png")

    first = await provider.embed_image(image)
    second = await provider.embed_image(image)

    assert first == pytest.approx(second, abs=1e-5)


async def test_text_ranks_the_matching_color_image_higher(
    provider: ClipEmbeddingProvider,
) -> None:
    red_image = await provider.embed_image(
        ImageRef(photo_id=uuid.uuid4(), path=FIXTURES_DIR / "red.png")
    )
    blue_image = await provider.embed_image(
        ImageRef(photo_id=uuid.uuid4(), path=FIXTURES_DIR / "blue.png")
    )
    red_text = await provider.embed_text("a photo of the color red")
    blue_text = await provider.embed_text("a photo of the color blue")

    assert _cosine_similarity(red_image, red_text) > _cosine_similarity(red_image, blue_text)
    assert _cosine_similarity(blue_image, blue_text) > _cosine_similarity(blue_image, red_text)


async def test_image_and_text_embeddings_share_the_same_dimensionality(
    provider: ClipEmbeddingProvider,
) -> None:
    image = await provider.embed_image(
        ImageRef(photo_id=uuid.uuid4(), path=FIXTURES_DIR / "red.png")
    )
    text = await provider.embed_text("a photo of the color red")

    assert len(image) == len(text) == 512
