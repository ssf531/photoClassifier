import uuid
from pathlib import Path

from core.domain.providers import ImageRef
from core.infrastructure.quality_provider import (
    MODEL_VERSION,
    PROVIDER_ID,
    QualityAssessmentProvider,
)

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "quality"


def _image_ref(filename: str) -> ImageRef:
    return ImageRef(photo_id=uuid.uuid4(), path=FIXTURES_DIR / filename)


async def test_result_carries_provider_identity() -> None:
    provider = QualityAssessmentProvider()

    result = await provider.assess(_image_ref("normal.png"))

    assert result.provider_id == PROVIDER_ID
    assert result.model_version == MODEL_VERSION
    assert result.confidence == 1.0


async def test_sharp_image_is_not_flagged_blurry() -> None:
    provider = QualityAssessmentProvider()

    result = await provider.assess(_image_ref("sharp.png"))

    assert result.raw_payload["is_blurry"] is False


async def test_blurry_image_is_flagged_blurry() -> None:
    provider = QualityAssessmentProvider()

    result = await provider.assess(_image_ref("blurry.png"))

    assert result.raw_payload["is_blurry"] is True


async def test_blurry_image_scores_lower_sharpness_than_sharp_image() -> None:
    provider = QualityAssessmentProvider()

    sharp = await provider.assess(_image_ref("sharp.png"))
    blurry = await provider.assess(_image_ref("blurry.png"))

    assert blurry.raw_payload["sharpness_variance"] < sharp.raw_payload["sharpness_variance"]


async def test_overexposed_image_is_flagged() -> None:
    provider = QualityAssessmentProvider()

    result = await provider.assess(_image_ref("overexposed.png"))

    assert result.raw_payload["is_overexposed"] is True
    assert result.raw_payload["is_underexposed"] is False


async def test_underexposed_image_is_flagged() -> None:
    provider = QualityAssessmentProvider()

    result = await provider.assess(_image_ref("underexposed.png"))

    assert result.raw_payload["is_underexposed"] is True
    assert result.raw_payload["is_overexposed"] is False


async def test_normal_image_is_not_flagged_either_way() -> None:
    provider = QualityAssessmentProvider()

    result = await provider.assess(_image_ref("normal.png"))

    assert result.raw_payload["is_underexposed"] is False
    assert result.raw_payload["is_overexposed"] is False
