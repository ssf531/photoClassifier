import asyncio
import os
import time
from collections.abc import Callable
from pathlib import Path

from core.domain.thumbnails import ThumbSize
from core.infrastructure.raster_thumbnail import ThumbnailResult


class ThumbnailCacheManager:
    """On-disk cache keyed by content_hash + size bucket (SDD §12).

    Never stored in the DB. LRU eviction (by file mtime) against a
    configurable size cap. Request coalescing for concurrent identical
    requests is TASK-0B's concern (the HTTP endpoint), not this manager's.
    """

    def __init__(self, cache_dir: Path, max_size_bytes: int) -> None:
        self._cache_dir = cache_dir
        self._max_size_bytes = max_size_bytes

    def cache_path(self, content_hash: str, size: ThumbSize) -> Path:
        return self._cache_dir / f"{content_hash}_{size.value}.jpg"

    async def ensure(
        self,
        content_hash: str,
        size: ThumbSize,
        generate: Callable[[], ThumbnailResult],
    ) -> Path:
        path = self.cache_path(content_hash, size)
        if path.is_file():
            self._touch(path)
            return path

        result = await asyncio.to_thread(generate)

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(path.name + ".tmp")
        tmp_path.write_bytes(result.data)
        tmp_path.replace(path)

        self._evict_if_over_cap()
        return path

    def _touch(self, path: Path) -> None:
        now = time.time()
        os.utime(path, (now, now))

    def _entries(self) -> list[tuple[Path, os.stat_result]]:
        if not self._cache_dir.is_dir():
            return []
        return [(p, p.stat()) for p in self._cache_dir.glob("*.jpg") if p.is_file()]

    def total_size_bytes(self) -> int:
        return sum(st.st_size for _, st in self._entries())

    def _evict_if_over_cap(self) -> None:
        entries = self._entries()
        total = sum(st.st_size for _, st in entries)
        if total <= self._max_size_bytes:
            return

        entries.sort(key=lambda item: item[1].st_mtime)  # oldest (least recently used) first
        for path, st in entries:
            if total <= self._max_size_bytes:
                break
            path.unlink(missing_ok=True)
            total -= st.st_size
