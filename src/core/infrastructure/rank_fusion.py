from collections.abc import Sequence

from core.domain.library import PhotoId

DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[PhotoId]], *, k: int = DEFAULT_RRF_K
) -> list[tuple[PhotoId, float]]:
    """Reciprocal Rank Fusion (SDD §7.2): combines multiple ranked lists
    (e.g. BM25 text rank, cosine-similarity vector rank) into one fused
    ranking without needing to normalize their incomparable raw scores --
    only each list's rank *position* is used, never its score. `k` dampens
    the influence of any single high rank (60 is the standard default from
    the original RRF paper).
    """
    scores: dict[PhotoId, float] = {}
    for ranked_list in ranked_lists:
        for position, photo_id in enumerate(ranked_list, start=1):
            scores[photo_id] = scores.get(photo_id, 0.0) + 1.0 / (k + position)

    return sorted(scores.items(), key=lambda item: item[1], reverse=True)
