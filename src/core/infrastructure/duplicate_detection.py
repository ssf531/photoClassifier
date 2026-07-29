import asyncio
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps

from core.domain.providers import (
    DuplicateCandidate,
    DuplicateGroupMemberResult,
    DuplicateGroupResult,
)

DETECTION_METHOD = "dhash@1"
DEFAULT_HASH_SIZE = 8
DEFAULT_MAX_HAMMING_DISTANCE = 5


def compute_dhash(path: Path, hash_size: int = DEFAULT_HASH_SIZE) -> int:
    """Difference hash (SDD §6.1: "Perceptual hash (pHash/dHash)"): robust to
    resizing and recompression, unlike a content hash, so it catches the
    "same photo, exported twice" case the change-detection content hash misses.
    """
    with Image.open(path) as raw_image:
        oriented = ImageOps.exif_transpose(raw_image) or raw_image
        gray = oriented.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
        pixels = list(gray.getdata())

    bits = 0
    for row in range(hash_size):
        row_start = row * (hash_size + 1)
        for col in range(hash_size):
            bits = (bits << 1) | int(pixels[row_start + col] > pixels[row_start + col + 1])
    return bits


def hamming_distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _keeper_sort_key(candidate: DuplicateCandidate) -> tuple[int, datetime]:
    """Highest resolution first, then earliest capture time (SDD §10); a
    photo with no known capture time sorts last among otherwise-equal ties."""
    resolution = -(candidate.width * candidate.height)
    captured_at = candidate.captured_at or datetime.max.replace(tzinfo=timezone.utc)  # noqa: UP017
    return (resolution, captured_at)


async def find_duplicate_groups(
    candidates: Sequence[DuplicateCandidate],
    *,
    hash_size: int = DEFAULT_HASH_SIZE,
    max_hamming_distance: int = DEFAULT_MAX_HAMMING_DISTANCE,
) -> list[DuplicateGroupResult]:
    """Group near-duplicate photos by dHash similarity, clustering with a
    union-find over all pairs within `max_hamming_distance`, then recommend a
    keeper per group: highest resolution, then earliest capture time (SDD §10).
    Singletons (no near-duplicate found) are not returned as a group.
    """
    hashes = await asyncio.gather(
        *(asyncio.to_thread(compute_dhash, c.path, hash_size) for c in candidates)
    )

    parent = list(range(len(candidates)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        root_i, root_j = find(i), find(j)
        if root_i != root_j:
            parent[root_j] = root_i

    max_bits = hash_size * hash_size
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            if hamming_distance(hashes[i], hashes[j]) <= max_hamming_distance:
                union(i, j)

    clusters: dict[int, list[int]] = {}
    for index in range(len(candidates)):
        clusters.setdefault(find(index), []).append(index)

    groups: list[DuplicateGroupResult] = []
    for member_indexes in clusters.values():
        if len(member_indexes) < 2:
            continue

        keeper_index = min(member_indexes, key=lambda i: _keeper_sort_key(candidates[i]))
        members = [
            DuplicateGroupMemberResult(
                photo_id=candidates[i].photo_id,
                similarity_score=(
                    1.0 - hamming_distance(hashes[i], hashes[keeper_index]) / max_bits
                ),
                is_recommended_keeper=(i == keeper_index),
            )
            for i in member_indexes
        ]
        groups.append(DuplicateGroupResult(detection_method=DETECTION_METHOD, members=members))

    return groups
