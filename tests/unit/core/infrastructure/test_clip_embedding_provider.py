import asyncio
import uuid
from pathlib import Path

import pytest

from core.domain.providers import ImageRef
from core.infrastructure.clip_embedding_provider import (
    ClipEmbeddingProvider,
    ClipModelUnavailableError,
)


def _provider(cache_dir: Path) -> ClipEmbeddingProvider:
    return ClipEmbeddingProvider(cache_dir, asyncio.Semaphore(1))


def test_is_available_false_when_no_model_files_present(tmp_path: Path) -> None:
    assert _provider(tmp_path).is_available() is False


async def test_embed_image_raises_when_model_unavailable(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    image = ImageRef(photo_id=uuid.uuid4(), path=tmp_path / "does-not-matter.jpg")

    with pytest.raises(ClipModelUnavailableError):
        await provider.embed_image(image)


async def test_embed_text_raises_when_model_unavailable(tmp_path: Path) -> None:
    provider = _provider(tmp_path)

    with pytest.raises(ClipModelUnavailableError):
        await provider.embed_text("a photo of a cat")
