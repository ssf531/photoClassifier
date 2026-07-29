import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.domain.providers import DuplicateCandidate
from core.infrastructure.duplicate_detection import (
    compute_dhash,
    find_duplicate_groups,
    hamming_distance,
)

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "duplicates"


def _candidate(
    filename: str, width: int, height: int, captured_at: datetime | None = None
) -> DuplicateCandidate:
    return DuplicateCandidate(
        photo_id=uuid.uuid4(),
        path=FIXTURES_DIR / filename,
        width=width,
        height=height,
        captured_at=captured_at,
    )


def test_hamming_distance_is_zero_for_identical_hashes() -> None:
    h = compute_dhash(FIXTURES_DIR / "original.jpg")

    assert hamming_distance(h, h) == 0


def test_exact_duplicate_and_resized_recompressed_hash_close_to_original() -> None:
    original = compute_dhash(FIXTURES_DIR / "original.jpg")
    exact = compute_dhash(FIXTURES_DIR / "exact_duplicate.jpg")
    resized = compute_dhash(FIXTURES_DIR / "resized_recompressed.jpg")

    assert hamming_distance(original, exact) <= 5
    assert hamming_distance(original, resized) <= 5


def test_unrelated_image_hashes_far_from_original() -> None:
    original = compute_dhash(FIXTURES_DIR / "original.jpg")
    unrelated = compute_dhash(FIXTURES_DIR / "unrelated.jpg")

    assert hamming_distance(original, unrelated) > 5


async def test_groups_exact_and_near_duplicates_together_excluding_unrelated() -> None:
    original = _candidate("original.jpg", 256, 256)
    exact = _candidate("exact_duplicate.jpg", 256, 256)
    resized = _candidate("resized_recompressed.jpg", 128, 128)
    unrelated = _candidate("unrelated.jpg", 256, 256)

    groups = await find_duplicate_groups([original, exact, resized, unrelated])

    assert len(groups) == 1
    member_ids = {member.photo_id for member in groups[0].members}
    assert member_ids == {original.photo_id, exact.photo_id, resized.photo_id}


async def test_no_groups_when_all_images_are_unrelated() -> None:
    a = _candidate("original.jpg", 256, 256)
    b = _candidate("unrelated.jpg", 256, 256)

    groups = await find_duplicate_groups([a, b])

    assert groups == []


async def test_recommended_keeper_is_the_highest_resolution_member() -> None:
    original = _candidate("original.jpg", 256, 256)
    exact = _candidate("exact_duplicate.jpg", 256, 256)
    resized = _candidate("resized_recompressed.jpg", 128, 128)

    (group,) = await find_duplicate_groups([original, exact, resized])

    keepers = [m for m in group.members if m.is_recommended_keeper]
    assert len(keepers) == 1
    assert keepers[0].photo_id in {original.photo_id, exact.photo_id}
    assert keepers[0].photo_id != resized.photo_id


async def test_recommended_keeper_breaks_resolution_tie_with_earliest_capture_time() -> None:
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    original = _candidate("original.jpg", 256, 256, captured_at=now)
    exact_earlier = _candidate("exact_duplicate.jpg", 256, 256, captured_at=now - timedelta(days=1))

    (group,) = await find_duplicate_groups([original, exact_earlier])

    keepers = [m for m in group.members if m.is_recommended_keeper]
    assert len(keepers) == 1
    assert keepers[0].photo_id == exact_earlier.photo_id


async def test_keeper_similarity_score_is_one() -> None:
    original = _candidate("original.jpg", 256, 256)
    exact = _candidate("exact_duplicate.jpg", 256, 256)

    (group,) = await find_duplicate_groups([original, exact])

    keeper = next(m for m in group.members if m.is_recommended_keeper)
    assert keeper.similarity_score == 1.0
