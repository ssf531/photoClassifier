from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

from core.infrastructure.raw_thumbnail import generate_raw_thumbnail


def _fake_raw_context(rgb_array: np.ndarray) -> MagicMock:
    """A fake rawpy.RawPy context manager, since a genuine RAW fixture isn't
    obtainable in this environment. This tests our own wrapper logic
    (orientation application, resize, flatten, JPEG encode) end-to-end;
    rawpy/LibRaw's own decode correctness is out of scope here -- that's a
    mature, independently-tested C library, not something this task re-verifies.
    """
    raw = MagicMock()
    raw.postprocess.return_value = rgb_array
    context = MagicMock()
    context.__enter__.return_value = raw
    context.__exit__.return_value = False
    return context


def _landscape_array() -> np.ndarray:
    arr = np.zeros((30, 60, 3), dtype=np.uint8)
    arr[:15, :, :] = [255, 0, 0]
    arr[15:, :, :] = [0, 0, 255]
    return arr


def test_generate_raw_thumbnail_calls_rawpy_with_expected_options(tmp_path: Path) -> None:
    source = tmp_path / "photo.CR2"
    source.write_bytes(b"not a real raw file")

    with patch("core.infrastructure.raw_thumbnail.rawpy.imread") as mock_imread:
        mock_imread.return_value = _fake_raw_context(_landscape_array())
        generate_raw_thumbnail(source, max_dimension=100)

    mock_imread.assert_called_once_with(str(source))


def test_generate_raw_thumbnail_returns_upright_image_without_orientation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "photo.NEF"

    with patch("core.infrastructure.raw_thumbnail.rawpy.imread") as mock_imread:
        mock_imread.return_value = _fake_raw_context(_landscape_array())
        result = generate_raw_thumbnail(source, max_dimension=100)

    assert result.format == "JPEG"
    assert result.width == 60
    assert result.height == 30


def test_generate_raw_thumbnail_applies_explicit_orientation(tmp_path: Path) -> None:
    source = tmp_path / "photo.ARW"

    with patch("core.infrastructure.raw_thumbnail.rawpy.imread") as mock_imread:
        # stored as if rotated 90 CW needed (orientation 6): stored buffer is
        # portrait (30 wide x 60 tall); corrected output should be landscape.
        stored = np.zeros((60, 30, 3), dtype=np.uint8)
        mock_imread.return_value = _fake_raw_context(stored)
        result = generate_raw_thumbnail(source, max_dimension=200, orientation=6)

    assert result.width == 60
    assert result.height == 30


def test_generate_raw_thumbnail_downscales_preserving_aspect_ratio(tmp_path: Path) -> None:
    source = tmp_path / "photo.DNG"

    with patch("core.infrastructure.raw_thumbnail.rawpy.imread") as mock_imread:
        mock_imread.return_value = _fake_raw_context(_landscape_array())
        result = generate_raw_thumbnail(source, max_dimension=20)

    assert result.width == 20
    assert result.height == 10


def test_generate_raw_thumbnail_produces_decodable_jpeg_bytes(tmp_path: Path) -> None:
    source = tmp_path / "photo.CR3"

    with patch("core.infrastructure.raw_thumbnail.rawpy.imread") as mock_imread:
        mock_imread.return_value = _fake_raw_context(_landscape_array())
        result = generate_raw_thumbnail(source, max_dimension=100)

    image = Image.open(BytesIO(result.data))
    assert image.format == "JPEG"
    assert image.mode == "RGB"
