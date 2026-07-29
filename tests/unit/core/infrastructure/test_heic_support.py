import importlib.util
import sys
from pathlib import Path

import pytest

import core.infrastructure.heic_support as heic_support_module
from core.infrastructure.heic_support import is_heic_supported
from core.infrastructure.raster_thumbnail import generate_thumbnail

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "thumbnails"
PILLOW_HEIF_INSTALLED = importlib.util.find_spec("pillow_heif") is not None


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    heic_support_module._heic_available = None
    yield
    heic_support_module._heic_available = None


def test_is_heic_supported_reflects_real_environment() -> None:
    # pillow-heif is an optional install; this asserts the detection logic
    # actually reflects the real environment, not just that it returns a bool.
    assert is_heic_supported() is PILLOW_HEIF_INSTALLED


def test_is_heic_supported_returns_false_when_pillow_heif_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "pillow_heif", None)

    assert is_heic_supported() is False


def test_is_heic_supported_result_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    first = is_heic_supported()
    monkeypatch.setitem(sys.modules, "pillow_heif", None)

    assert is_heic_supported() == first


@pytest.mark.skipif(not PILLOW_HEIF_INSTALLED, reason="pillow-heif not installed")
def test_heic_thumbnail_generates_transparently_once_registered() -> None:
    assert is_heic_supported() is True

    result = generate_thumbnail(FIXTURES_DIR / "plain.heic", max_dimension=100)

    assert result.format == "JPEG"
    assert result.width == 60
    assert result.height == 30
