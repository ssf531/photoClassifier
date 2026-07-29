import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.domain.library import HEIC_EXTENSIONS, RAW_EXTENSIONS
from core.domain.thumbnails import ThumbSize
from core.infrastructure.heic_support import is_heic_supported
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.metadata_repository import MetadataRepository
from core.infrastructure.raster_thumbnail import ThumbnailResult, generate_thumbnail
from core.infrastructure.raw_thumbnail import generate_raw_thumbnail
from core.infrastructure.thumbnail_cache import ThumbnailCacheManager


class PhotoNotFoundError(Exception):
    pass


class PhotoNotHashedError(Exception):
    pass


@dataclass(frozen=True)
class ThumbnailOutcome:
    etag: str
    path: Path | None
    degraded_reason: str | None = None


class ThumbnailService:
    """Orchestrates the /api/v1/thumbnails/{photo_id} use case (SDD §16.7):
    resolves the photo's file, picks the raster/RAW generator, applies the
    HEIC-unavailable degraded path (ADR-0012), and coalesces concurrent
    requests for the same (content_hash, size) so only one generation runs.
    """

    def __init__(
        self,
        cache: ThumbnailCacheManager,
        photo_repo: PhotoRepository,
        library_root_repo: LibraryRootRepository,
        metadata_repo: MetadataRepository,
        grid_size_px: int,
        preview_size_px: int,
    ) -> None:
        self._cache = cache
        self._photo_repo = photo_repo
        self._library_root_repo = library_root_repo
        self._metadata_repo = metadata_repo
        self._size_px = {ThumbSize.GRID: grid_size_px, ThumbSize.PREVIEW: preview_size_px}
        self._in_flight: dict[tuple[str, ThumbSize], asyncio.Task[Path]] = {}

    async def get_or_generate(self, photo_id: uuid.UUID, size: ThumbSize) -> ThumbnailOutcome:
        photo = await self._photo_repo.get(photo_id)
        if photo is None:
            raise PhotoNotFoundError(str(photo_id))
        if photo.content_hash is None:
            raise PhotoNotHashedError(str(photo_id))

        etag = f'"{photo.content_hash}-{size.value}"'

        root = await self._library_root_repo.get(photo.library_root_id)
        if root is None:
            raise PhotoNotFoundError(str(photo_id))
        photo_path = Path(root.path) / photo.relative_path
        suffix = photo_path.suffix.lower()

        if suffix in HEIC_EXTENSIONS and not is_heic_supported():
            return ThumbnailOutcome(etag=etag, path=None, degraded_reason="heic-not-supported")

        size_px = self._size_px[size]
        generate = await self._make_generator(photo_id, photo_path, suffix, size_px)

        path = await self._ensure_coalesced(photo.content_hash, size, generate)
        return ThumbnailOutcome(etag=etag, path=path)

    async def _make_generator(
        self, photo_id: uuid.UUID, photo_path: Path, suffix: str, size_px: int
    ) -> Callable[[], ThumbnailResult]:
        if suffix not in RAW_EXTENSIONS:
            return lambda: generate_thumbnail(photo_path, size_px)

        metadata = await self._metadata_repo.get_by_photo_id(photo_id)
        orientation = metadata.orientation if metadata is not None else None
        return lambda: generate_raw_thumbnail(photo_path, size_px, orientation)

    async def _ensure_coalesced(
        self, content_hash: str, size: ThumbSize, generate: Callable[[], ThumbnailResult]
    ) -> Path:
        key = (content_hash, size)
        existing = self._in_flight.get(key)
        if existing is not None:
            return await existing

        task = asyncio.ensure_future(self._cache.ensure(content_hash, size, generate))
        self._in_flight[key] = task
        try:
            return await task
        finally:
            self._in_flight.pop(key, None)
