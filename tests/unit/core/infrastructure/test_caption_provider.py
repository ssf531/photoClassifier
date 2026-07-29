import asyncio
import uuid
from pathlib import Path

import pytest

from core.domain.providers import ImageRef
from core.infrastructure.caption_provider import (
    CaptioningProvider,
    CaptionModelUnavailableError,
)


def _provider(cache_dir: Path) -> CaptioningProvider:
    return CaptioningProvider(cache_dir, asyncio.Semaphore(1))


def test_is_available_false_when_no_model_files_present(tmp_path: Path) -> None:
    assert _provider(tmp_path).is_available() is False


async def test_caption_raises_when_model_unavailable(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    image = ImageRef(photo_id=uuid.uuid4(), path=tmp_path / "does-not-matter.jpg")

    with pytest.raises(CaptionModelUnavailableError):
        await provider.caption(image)
