import asyncio
from pathlib import Path

import httpx
import numpy as np
import onnxruntime as ort
from numpy.typing import NDArray
from PIL import Image, ImageOps
from tokenizers import Tokenizer

from core.domain.providers import CaptionResult, ImageRef
from core.infrastructure.model_acquisition import (
    download_model,
    is_model_available,
    resolve_model_path,
)

PROVIDER_ID = "vit-gpt2-image-captioning"
MODEL_VERSION = "vit-gpt2-image-captioning@1"

ENCODER_FILENAME = "encoder_model_quantized.onnx"
DECODER_FILENAME = "decoder_model_quantized.onnx"
TOKENIZER_FILENAME = "tokenizer.json"
_REQUIRED_FILENAMES = (ENCODER_FILENAME, DECODER_FILENAME, TOKENIZER_FILENAME)

# Xenova/vit-gpt2-image-captioning: a transformers.js ONNX export of
# nlpconnect/vit-gpt2-image-captioning (ViT encoder, GPT-2 decoder). This
# uses the plain (non-KV-cached) decoder graph: each generation step re-feeds
# the whole token sequence so far rather than threading past_key_values
# through, trading some redundant compute for a much simpler, easier-to-get-
# right generation loop -- captions are short (<= MAX_CAPTION_TOKENS), so the
# quadratic cost stays negligible relative to CPU captioning's already-known
# throughput ceiling (TD-12).
_MODEL_REPO_BASE_URL = "https://huggingface.co/Xenova/vit-gpt2-image-captioning/resolve/main"

IMAGE_SIZE = 224
IMAGE_MEAN = (0.5, 0.5, 0.5)
IMAGE_STD = (0.5, 0.5, 0.5)
EOS_TOKEN_ID = 50256
MAX_CAPTION_TOKENS = 24


class CaptionModelUnavailableError(Exception):
    pass


class CaptioningProvider:
    """Image captioning via ONNX Runtime (SDD §6.1/§6.5). Loads its sessions
    and tokenizer lazily on first use, so constructing this provider never
    requires the model to already be present (SDD §16.4).
    """

    provider_id = PROVIDER_ID
    model_version = MODEL_VERSION

    def __init__(
        self,
        cache_dir: Path,
        semaphore: asyncio.Semaphore,
        execution_provider: str = "CPUExecutionProvider",
        max_tokens: int = MAX_CAPTION_TOKENS,
    ) -> None:
        self._cache_dir = cache_dir
        self._semaphore = semaphore
        self._execution_provider = execution_provider
        self._max_tokens = max_tokens
        self._encoder_session: ort.InferenceSession | None = None
        self._decoder_session: ort.InferenceSession | None = None
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

    async def caption(self, image: ImageRef) -> CaptionResult:
        self._ensure_loaded()
        async with self._semaphore:
            return await asyncio.to_thread(self._caption_sync, image.path)

    def _ensure_loaded(self) -> None:
        if self._encoder_session is not None:
            return
        if not self.is_available():
            raise CaptionModelUnavailableError(PROVIDER_ID)

        encoder_path = resolve_model_path(self._cache_dir, PROVIDER_ID, ENCODER_FILENAME)
        decoder_path = resolve_model_path(self._cache_dir, PROVIDER_ID, DECODER_FILENAME)
        tokenizer_path = resolve_model_path(self._cache_dir, PROVIDER_ID, TOKENIZER_FILENAME)

        self._encoder_session = ort.InferenceSession(
            str(encoder_path), providers=[self._execution_provider]
        )
        self._decoder_session = ort.InferenceSession(
            str(decoder_path), providers=[self._execution_provider]
        )
        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))

    def _caption_sync(self, path: Path) -> CaptionResult:
        assert self._encoder_session is not None
        assert self._decoder_session is not None
        assert self._tokenizer is not None

        pixel_values = _preprocess_image(path)
        (encoder_hidden_states,) = self._encoder_session.run(None, {"pixel_values": pixel_values})

        token_ids = [EOS_TOKEN_ID]  # GPT-2's <|endoftext|> doubles as BOS here
        token_probabilities: list[float] = []
        for _ in range(self._max_tokens):
            input_ids = np.array([token_ids], dtype=np.int64)
            (logits,) = self._decoder_session.run(
                ["logits"],
                {"input_ids": input_ids, "encoder_hidden_states": encoder_hidden_states},
            )
            next_token_logits = logits[0, -1]
            next_token_id = int(np.argmax(next_token_logits))
            if next_token_id == EOS_TOKEN_ID:
                break
            token_probabilities.append(float(_softmax(next_token_logits)[next_token_id]))
            token_ids.append(next_token_id)

        caption_text = self._tokenizer.decode(token_ids[1:]).strip()
        confidence = float(np.mean(token_probabilities)) if token_probabilities else 0.0
        return CaptionResult(
            provider_id=PROVIDER_ID,
            model_version=MODEL_VERSION,
            confidence=confidence,
            raw_payload={"caption": caption_text},
        )


def _softmax(logits: NDArray[np.float32]) -> NDArray[np.float32]:
    shifted = logits - np.max(logits)
    exponentiated = np.exp(shifted)
    result: NDArray[np.float32] = exponentiated / exponentiated.sum()
    return result


def _preprocess_image(path: Path) -> NDArray[np.float32]:
    """Direct resize to 224x224 (no aspect-preserving crop), rescale,
    normalize, NCHW -- matching the model's `preprocessor_config.json`."""
    with Image.open(path) as raw_image:
        oriented = ImageOps.exif_transpose(raw_image) or raw_image
        rgb = oriented.convert("RGB")

    resized = rgb.resize((IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.BILINEAR)
    array = np.asarray(resized, dtype=np.float32) / np.float32(255.0)
    array = (
        (array - np.array(IMAGE_MEAN, dtype=np.float32)) / np.array(IMAGE_STD, dtype=np.float32)
    ).astype(np.float32)
    array = array.transpose(2, 0, 1).astype(np.float32)
    return array[np.newaxis, :, :, :]
