from io import BytesIO
from pathlib import Path

from PIL import Image

from core.infrastructure.raster_thumbnail import ThumbnailResult, apply_orientation, flatten_to_rgb


def generate_raw_thumbnail(
    source_path: Path, max_dimension: int, orientation: int | None = None
) -> ThumbnailResult:
    """Generate a thumbnail for a camera RAW file via rawpy/LibRaw (ADR-0012: bundled).

    RAW decode produces a bare numpy array with no EXIF attached, so unlike
    the raster path, orientation must be supplied explicitly by the caller
    (e.g. from the photo's already-normalized metadata) rather than read from
    the file itself.
    """
    # Deferred to first real use (SDD §3.14): a frozen build shouldn't pay
    # rawpy/LibRaw's import cost for users who never open a RAW file.
    import rawpy

    with rawpy.imread(str(source_path)) as raw:
        rgb_array = raw.postprocess(use_camera_wb=True, half_size=True, no_auto_bright=False)

    image = Image.fromarray(rgb_array)
    upright = apply_orientation(image, orientation)
    upright.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    rgb = flatten_to_rgb(upright)

    buffer = BytesIO()
    rgb.save(buffer, format="JPEG", quality=85)
    width, height = rgb.size

    return ThumbnailResult(data=buffer.getvalue(), width=width, height=height, format="JPEG")
