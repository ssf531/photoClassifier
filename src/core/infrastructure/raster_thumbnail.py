from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

_TRANSPARENT_MODES = {"RGBA", "LA"}
_EXIF_ORIENTATION_TAG = 0x0112


@dataclass(frozen=True)
class ThumbnailResult:
    data: bytes
    width: int
    height: int
    format: str


def flatten_to_rgb(image: Image.Image) -> Image.Image:
    has_transparency = image.mode in _TRANSPARENT_MODES or (
        image.mode == "P" and "transparency" in image.info
    )
    if has_transparency:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def apply_orientation(image: Image.Image, orientation: int | None) -> Image.Image:
    """Correct an image with no embedded EXIF (e.g. a rawpy-decoded array)
    for a known orientation code, reusing Pillow's own exif_transpose logic
    rather than re-implementing the 8-way rotation/flip table by hand.
    """
    if orientation is None or orientation == 1:
        return image
    tagged = image.copy()
    tagged.getexif()[_EXIF_ORIENTATION_TAG] = orientation
    return ImageOps.exif_transpose(tagged)


def generate_thumbnail(source_path: Path, max_dimension: int) -> ThumbnailResult:
    """Generate an upright, bounded-size JPEG thumbnail for a raster image.

    Applies EXIF orientation correction (Pillow's exif_transpose) before
    resizing, so the output is always "as viewed" regardless of how the
    camera stored the pixels. `max_dimension` bounds the longer side;
    aspect ratio is preserved. Also handles HEIC/HEIF transparently once
    `pillow_heif.register_heif_opener()` has been called (see heic_support.py).
    """
    with Image.open(source_path) as opened:
        upright = ImageOps.exif_transpose(opened)
        upright.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        rgb = flatten_to_rgb(upright)

        buffer = BytesIO()
        rgb.save(buffer, format="JPEG", quality=85)
        width, height = rgb.size

    return ThumbnailResult(data=buffer.getvalue(), width=width, height=height, format="JPEG")
