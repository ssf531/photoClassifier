import time
from pathlib import Path

from core.domain.thumbnails import ThumbSize
from core.infrastructure.raster_thumbnail import ThumbnailResult
from core.infrastructure.thumbnail_cache import ThumbnailCacheManager


def _fake_result(size_bytes: int) -> ThumbnailResult:
    return ThumbnailResult(data=b"x" * size_bytes, width=10, height=10, format="JPEG")


def test_cache_path_is_keyed_by_content_hash_and_size_bucket(tmp_path: Path) -> None:
    manager = ThumbnailCacheManager(tmp_path, max_size_bytes=10_000)

    grid_path = manager.cache_path("abc123", ThumbSize.GRID)
    preview_path = manager.cache_path("abc123", ThumbSize.PREVIEW)

    assert grid_path != preview_path
    assert "abc123" in grid_path.name
    assert "grid" in grid_path.name
    assert "preview" in preview_path.name


async def test_ensure_generates_on_first_call_and_writes_to_disk(tmp_path: Path) -> None:
    manager = ThumbnailCacheManager(tmp_path, max_size_bytes=10_000)
    calls = []

    def generate() -> ThumbnailResult:
        calls.append(1)
        return _fake_result(100)

    path = await manager.ensure("hash1", ThumbSize.GRID, generate)

    assert path.is_file()
    assert path.read_bytes() == b"x" * 100
    assert len(calls) == 1


async def test_ensure_reuses_cached_file_without_regenerating(tmp_path: Path) -> None:
    manager = ThumbnailCacheManager(tmp_path, max_size_bytes=10_000)
    calls = []

    def generate() -> ThumbnailResult:
        calls.append(1)
        return _fake_result(100)

    await manager.ensure("hash1", ThumbSize.GRID, generate)
    await manager.ensure("hash1", ThumbSize.GRID, generate)

    assert len(calls) == 1


async def test_eviction_keeps_total_size_within_cap(tmp_path: Path) -> None:
    manager = ThumbnailCacheManager(tmp_path, max_size_bytes=250)

    for i in range(5):
        await manager.ensure(f"hash{i}", ThumbSize.GRID, lambda: _fake_result(100))
        time.sleep(0.01)  # ensure distinct mtimes for deterministic LRU ordering

    assert manager.total_size_bytes() <= 250


async def test_eviction_removes_least_recently_used_first(tmp_path: Path) -> None:
    manager = ThumbnailCacheManager(tmp_path, max_size_bytes=250)

    for i in range(3):
        await manager.ensure(f"hash{i}", ThumbSize.GRID, lambda: _fake_result(100))
        time.sleep(0.01)

    # hash0..hash2 exist, ~300 bytes total, over the 250 cap: hash0 (oldest) evicted
    assert not manager.cache_path("hash0", ThumbSize.GRID).is_file()
    assert manager.cache_path("hash2", ThumbSize.GRID).is_file()


async def test_touching_a_cache_hit_protects_it_from_eviction(tmp_path: Path) -> None:
    manager = ThumbnailCacheManager(tmp_path, max_size_bytes=250)

    await manager.ensure("old", ThumbSize.GRID, lambda: _fake_result(100))
    time.sleep(0.01)
    await manager.ensure("middle", ThumbSize.GRID, lambda: _fake_result(100))
    time.sleep(0.01)

    # touch "old" via a cache hit, making it more recently used than "middle"
    await manager.ensure("old", ThumbSize.GRID, lambda: _fake_result(100))
    time.sleep(0.01)

    # adding a third entry pushes total over cap; "middle" is now the LRU victim
    await manager.ensure("new", ThumbSize.GRID, lambda: _fake_result(100))

    assert manager.cache_path("old", ThumbSize.GRID).is_file()
    assert not manager.cache_path("middle", ThumbSize.GRID).is_file()
    assert manager.cache_path("new", ThumbSize.GRID).is_file()
