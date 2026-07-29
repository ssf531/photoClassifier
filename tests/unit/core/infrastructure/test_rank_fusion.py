import uuid

import pytest

from core.infrastructure.rank_fusion import reciprocal_rank_fusion


def test_document_in_both_lists_outranks_one_only_in_a_single_list() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    # text and vector retrieval disagree on order: text ranks a > b,
    # vector ranks b > c. b's presence in both lists should win overall.
    text_rank = [a, b]
    vector_rank = [b, c]

    fused = reciprocal_rank_fusion([text_rank, vector_rank])

    assert [photo_id for photo_id, _ in fused] == [b, a, c]


def test_fused_scores_match_a_hand_computed_rrf_reference() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    text_rank = [a, b]
    vector_rank = [b, c]

    fused = reciprocal_rank_fusion([text_rank, vector_rank], k=60)
    scores = dict(fused)

    assert scores[a] == pytest.approx(1 / 61)
    assert scores[b] == pytest.approx(1 / 62 + 1 / 61)
    assert scores[c] == pytest.approx(1 / 62)


def test_a_document_absent_from_a_list_gets_no_contribution_from_it() -> None:
    a = uuid.uuid4()

    fused = reciprocal_rank_fusion([[a], []], k=60)

    assert dict(fused) == {a: pytest.approx(1 / 61)}


def test_single_list_preserves_its_own_order() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    fused = reciprocal_rank_fusion([[a, b, c]])

    assert [photo_id for photo_id, _ in fused] == [a, b, c]


def test_no_lists_returns_empty() -> None:
    assert reciprocal_rank_fusion([]) == []
