import asyncio
from pathlib import Path

import httpx
import numpy as np
import onnxruntime as ort
from numpy.typing import NDArray
from PIL import Image, ImageOps
from tokenizers import Tokenizer

from core.domain.providers import ImageRef, Vector
from core.infrastructure.model_acquisition import (
    download_model,
    is_model_available,
    resolve_model_path,
)

PROVIDER_ID = "clip-vit-base-patch32"
MODEL_VERSION = "clip-vit-base-patch32-quantized@1"

VISION_MODEL_FILENAME = "vision_model_quantized.onnx"
TEXT_MODEL_FILENAME = "text_model_quantized.onnx"
TOKENIZER_FILENAME = "tokenizer.json"
_REQUIRED_FILENAMES = (VISION_MODEL_FILENAME, TEXT_MODEL_FILENAME, TOKENIZER_FILENAME)

# Xenova/clip-vit-base-patch32: a transformers.js ONNX export of OpenAI's
# CLIP ViT-B/32, split into standalone image/text encoder graphs that already
# apply the final projection -- each run() call returns the 512-dim joint
# embedding directly, ready for cosine similarity.
_MODEL_REPO_BASE_URL = "https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main"

IMAGE_SIZE = 224
IMAGE_MEAN = (0.48145466, 0.4578275, 0.40821073)
IMAGE_STD = (0.26862954, 0.26130258, 0.27577711)
MAX_TEXT_TOKENS = 77


class ClipModelUnavailableError(Exception):
    pass


class ClipEmbeddingProvider:
    """CLIP image/text embeddings via ONNX Runtime (SDD §6.1). Loads its
    session and tokenizer lazily on first use, so constructing this provider
    never requires the model to already be present -- only calling it does
    (SDD §16.4's "works with zero models" guarantee).
    """

    provider_id = PROVIDER_ID
    model_version = MODEL_VERSION

    def __init__(
        self,
        cache_dir: Path,
        semaphore: asyncio.Semaphore,
        execution_provider: str = "CPUExecutionProvider",
    ) -> None:
        self._cache_dir = cache_dir
        self._semaphore = semaphore
        self._execution_provider = execution_provider
        self._vision_session: ort.InferenceSession | None = None
        self._text_session: ort.InferenceSession | None = None
        self._tokenizer: Tokenizer | None = None

    def is_available(self) -> bool:
        return all(
            is_model_available(self._cache_dir, PROVIDER_ID, filename)
            for filename in _REQUIRED_FILENAMES
        )

    async def ensure_downloaded(self, *, client: httpx.AsyncClient) -> None:
        """Download-on-first-enable path (SDD §16.4): fetches whichever of
        the three required files aren't already cached."""
        for filename in _REQUIRED_FILENAMES:
            if is_model_available(self._cache_dir, PROVIDER_ID, filename):
                continue
            subdir = "onnx/" if filename.endswith(".onnx") else ""
            url = f"{_MODEL_REPO_BASE_URL}/{subdir}{filename}"
            await download_model(url, self._cache_dir, PROVIDER_ID, filename, client=client)

    async def embed_image(self, image: ImageRef) -> Vector:
        self._ensure_loaded()
        async with self._semaphore:
            return await asyncio.to_thread(self._embed_image_sync, image.path)

    async def embed_text(self, text: str) -> Vector:
        self._ensure_loaded()
        async with self._semaphore:
            return await asyncio.to_thread(self._embed_text_sync, text)

    def _ensure_loaded(self) -> None:
        if self._vision_session is not None:
            return
        if not self.is_available():
            raise ClipModelUnavailableError(PROVIDER_ID)

        vision_path = resolve_model_path(self._cache_dir, PROVIDER_ID, VISION_MODEL_FILENAME)
        text_path = resolve_model_path(self._cache_dir, PROVIDER_ID, TEXT_MODEL_FILENAME)
        tokenizer_path = resolve_model_path(self._cache_dir, PROVIDER_ID, TOKENIZER_FILENAME)

        self._vision_session = ort.InferenceSession(
            str(vision_path), providers=[self._execution_provider]
        )
        self._text_session = ort.InferenceSession(
            str(text_path), providers=[self._execution_provider]
        )
        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))

    def _embed_image_sync(self, path: Path) -> Vector:
        assert self._vision_session is not None
        pixel_values = _preprocess_image(path)
        (embeds,) = self._vision_session.run(None, {"pixel_values": pixel_values})
        return list(embeds[0].tolist())

    def _embed_text_sync(self, text: str) -> Vector:
        assert self._tokenizer is not None
        assert self._text_session is not None
        ids = self._tokenizer.encode(text).ids[:MAX_TEXT_TOKENS]
        input_ids = np.array([ids], dtype=np.int64)
        (embeds,) = self._text_session.run(None, {"input_ids": input_ids})
        return list(embeds[0].tolist())


def _preprocess_image(path: Path) -> NDArray[np.float32]:
    """Resize-shortest-edge to 224, center-crop, rescale, normalize, and
    reorder to NCHW -- matching the model's `preprocessor_config.json`
    exactly (bicubic resample, CLIP's standard mean/std).
    """
    with Image.open(path) as raw_image:
        oriented = ImageOps.exif_transpose(raw_image) or raw_image
        rgb = oriented.convert("RGB")

    width, height = rgb.size
    scale = IMAGE_SIZE / min(width, height)
    resized = rgb.resize((round(width * scale), round(height * scale)), Image.Resampling.BICUBIC)

    width, height = resized.size
    left = (width - IMAGE_SIZE) // 2
    top = (height - IMAGE_SIZE) // 2
    cropped = resized.crop((left, top, left + IMAGE_SIZE, top + IMAGE_SIZE))

    array = np.asarray(cropped, dtype=np.float32) / np.float32(255.0)
    array = (
        (array - np.array(IMAGE_MEAN, dtype=np.float32)) / np.array(IMAGE_STD, dtype=np.float32)
    ).astype(np.float32)
    array = array.transpose(2, 0, 1).astype(np.float32)
    return array[np.newaxis, :, :, :]
