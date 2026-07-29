import asyncio
import uuid
from pathlib import Path

import pytest

from core.domain.providers import ImageRef
from core.domain.settings import models_dir
from core.infrastructure.caption_provider import CaptioningProvider

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures"

pytestmark = pytest.mark.skipif(
    not CaptioningProvider(models_dir(), asyncio.Semaphore(1)).is_available(),
    reason="Captioning model not downloaded into the local model cache (TASK-0C acquisition path)",
)


@pytest.fixture
def provider() -> CaptioningProvider:
    return CaptioningProvider(models_dir(), asyncio.Semaphore(1))


async def test_caption_is_non_empty_and_carries_provider_identity(
    provider: CaptioningProvider,
) -> None:
    image = ImageRef(photo_id=uuid.uuid4(), path=FIXTURES_DIR / "clip" / "red.png")

    result = await provider.caption(image)

    assert result.provider_id == "vit-gpt2-image-captioning"
    assert result.model_version == "vit-gpt2-image-captioning@1"
    assert result.raw_payload["caption"] != ""
    assert 0.0 <= result.confidence <= 1.0


async def test_captions_a_fixed_fixture_set_with_plausible_non_empty_text(
    provider: CaptioningProvider,
) -> None:
    fixture_paths = [
        FIXTURES_DIR / "duplicates" / "original.jpg",
        FIXTURES_DIR / "duplicates" / "unrelated.jpg",
        FIXTURES_DIR / "quality" / "sharp.png",
    ]

    for path in fixture_paths:
        result = await provider.caption(ImageRef(photo_id=uuid.uuid4(), path=path))
        caption = result.raw_payload["caption"]
        assert isinstance(caption, str)
        assert len(caption.split()) >= 2
