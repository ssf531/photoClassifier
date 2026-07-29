import asyncio
import uuid
from pathlib import Path

import pytest

from core.domain.providers import ImageRef
from core.domain.settings import models_dir
from core.infrastructure.clip_embedding_provider import ClipEmbeddingProvider
from core.infrastructure.tag_provider import TaggingProvider

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "clip"

pytestmark = pytest.mark.skipif(
    not ClipEmbeddingProvider(models_dir(), asyncio.Semaphore(1)).is_available(),
    reason="CLIP model not downloaded into the local model cache (TASK-0C acquisition path)",
)


@pytest.fixture
def provider() -> TaggingProvider:
    embedding_provider = ClipEmbeddingProvider(models_dir(), asyncio.Semaphore(1))
    return TaggingProvider(embedding_provider)


async def test_red_image_is_tagged_with_the_red_color_label(provider: TaggingProvider) -> None:
    image = ImageRef(photo_id=uuid.uuid4(), path=FIXTURES_DIR / "red.png")

    result = await provider.tag(image)

    labels = [tag["label"] for tag in result.raw_payload["tags"]]
    assert "red color" in labels
    assert result.confidence >= 0.25


async def test_blue_image_is_tagged_with_the_blue_color_label(provider: TaggingProvider) -> None:
    image = ImageRef(photo_id=uuid.uuid4(), path=FIXTURES_DIR / "blue.png")

    result = await provider.tag(image)

    labels = [tag["label"] for tag in result.raw_payload["tags"]]
    assert "blue color" in labels


async def test_tags_are_returned_in_descending_confidence_order(
    provider: TaggingProvider,
) -> None:
    image = ImageRef(photo_id=uuid.uuid4(), path=FIXTURES_DIR / "red.png")

    result = await provider.tag(image)

    confidences = [tag["confidence"] for tag in result.raw_payload["tags"]]
    assert confidences == sorted(confidences, reverse=True)
    assert result.confidence == confidences[0]
