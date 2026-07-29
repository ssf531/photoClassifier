from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from core.infrastructure.raster_thumbnail import generate_thumbnail

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "thumbnails"


def _average_color(
    image: Image.Image, box: tuple[int, int, int, int]
) -> tuple[float, float, float]:
    region = image.crop(box)
    pixels = list(region.getdata())
    n = len(pixels)
    r = sum(p[0] for p in pixels) / n
    g = sum(p[1] for p in pixels) / n
    b = sum(p[2] for p in pixels) / n
    return r, g, b


def _load_result_image(data: bytes) -> Image.Image:
    return Image.open(BytesIO(data))


@pytest.mark.parametrize("orientation", [1, 2, 3, 4, 5, 6, 7, 8])
def test_thumbnail_is_upright_regardless_of_exif_orientation(orientation: int) -> None:
    source = FIXTURES_DIR / f"orientation_{orientation}.jpg"

    result = generate_thumbnail(source, max_dimension=100)

    # source is a 60x30 "landscape" reference; upright means wider than tall
    assert result.width == 60
    assert result.height == 30
    assert result.width > result.height

    image = _load_result_image(result.data)
    top_r, _, top_b = _average_color(image, (0, 0, 60, 7))
    bottom_r, _, bottom_b = _average_color(image, (0, 23, 60, 30))
    assert top_r > top_b  # top band is red
    assert bottom_b > bottom_r  # bottom band is blue


def test_no_orientation_tag_is_treated_as_upright() -> None:
    result = generate_thumbnail(FIXTURES_DIR / "no_orientation_tag.jpg", max_dimension=100)

    assert result.width == 60
    assert result.height == 30


def test_thumbnail_downscales_preserving_aspect_ratio() -> None:
    result = generate_thumbnail(FIXTURES_DIR / "orientation_1.jpg", max_dimension=20)

    assert result.width == 20
    assert result.height == 10


@pytest.mark.parametrize("filename", ["plain.tiff", "plain.webp", "plain.png"])
def test_supports_jpeg_png_tiff_webp(filename: str) -> None:
    result = generate_thumbnail(FIXTURES_DIR / filename, max_dimension=100)

    assert result.format == "JPEG"
    assert result.width == 60
    assert result.height == 30


def test_transparent_png_is_flattened_to_opaque_rgb() -> None:
    result = generate_thumbnail(FIXTURES_DIR / "transparent.png", max_dimension=100)

    image = _load_result_image(result.data)
    assert image.mode == "RGB"
    assert result.width == 40
    assert result.height == 20
