import asyncio

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps

from core.domain.providers import ImageRef, QualityResult

PROVIDER_ID = "builtin-quality"
MODEL_VERSION = "laplacian-exposure@1"

# Calibrated against tests/fixtures/quality: a heavily-blurred image scores
# ~1, a sharp or merely-textured one scores 80+, so 20 cleanly separates them.
BLUR_VARIANCE_THRESHOLD = 20.0
UNDEREXPOSED_MEAN_THRESHOLD = 40.0
OVEREXPOSED_MEAN_THRESHOLD = 215.0


class QualityAssessmentProvider:
    """Laplacian-variance sharpness + exposure statistics (SDD §6.1). Per the
    MVP Scope Overlay's TASK-045 revision, this is v1's entire `quality`
    capability -- the aesthetic-scoring model is deferred to v2, and neither
    of these signals needs a downloaded model (SDD §16.4).
    """

    provider_id = PROVIDER_ID
    model_version = MODEL_VERSION

    async def assess(self, image: ImageRef) -> QualityResult:
        return await asyncio.to_thread(self._assess_sync, image)

    def _assess_sync(self, image: ImageRef) -> QualityResult:
        with Image.open(image.path) as raw_image:
            oriented = ImageOps.exif_transpose(raw_image) or raw_image
            gray = np.asarray(oriented.convert("L"), dtype=np.float64)

        sharpness_variance = _laplacian_variance(gray)
        mean_brightness = float(gray.mean())

        raw_payload = {
            "sharpness_variance": sharpness_variance,
            "mean_brightness": mean_brightness,
            "is_blurry": sharpness_variance < BLUR_VARIANCE_THRESHOLD,
            "is_underexposed": mean_brightness < UNDEREXPOSED_MEAN_THRESHOLD,
            "is_overexposed": mean_brightness > OVEREXPOSED_MEAN_THRESHOLD,
        }
        return QualityResult(
            provider_id=PROVIDER_ID,
            model_version=MODEL_VERSION,
            confidence=1.0,
            raw_payload=raw_payload,
        )


def _laplacian_variance(gray: NDArray[np.float64]) -> float:
    """Variance of the discrete Laplacian: low for smooth/blurred images,
    high wherever sharp edges are present."""
    laplacian = (
        -4 * gray[1:-1, 1:-1] + gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:]
    )
    return float(laplacian.var())
