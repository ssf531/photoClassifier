import asyncio
import uuid

from core.domain.providers import ImageRef, Vector
from core.infrastructure.incremental_indexing import Debouncer, create_incremental_photo_indexer

DELAY = 0.05
MARGIN = 0.15


class _FakeEmbeddingService:
    def __init__(self) -> None:
        self.embed_calls: list[tuple[object, str]] = []

    async def embed(self, photo_id: object, provider: str) -> None:
        self.embed_calls.append((photo_id, provider))

    async def similar_to(self, photo_id: object, k: int) -> list[object]:  # pragma: no cover
        raise NotImplementedError

    async def embed_text(self, query: str, provider: str) -> Vector:  # pragma: no cover
        raise NotImplementedError

    async def embed_image(self, image: ImageRef) -> Vector:  # pragma: no cover
        raise NotImplementedError


async def test_rapid_triggers_for_the_same_key_produce_exactly_one_call() -> None:
    calls: list[object] = []

    async def callback(key: object) -> None:
        calls.append(key)

    debouncer = Debouncer(DELAY, callback)
    for _ in range(10):
        debouncer.trigger("photo-1")

    await asyncio.sleep(DELAY + MARGIN)

    assert calls == ["photo-1"]


async def test_different_keys_are_debounced_independently() -> None:
    calls: list[object] = []

    async def callback(key: object) -> None:
        calls.append(key)

    debouncer = Debouncer(DELAY, callback)
    debouncer.trigger("photo-1")
    debouncer.trigger("photo-2")

    await asyncio.sleep(DELAY + MARGIN)

    assert sorted(calls) == ["photo-1", "photo-2"]


async def test_retriggering_before_the_delay_elapses_resets_it() -> None:
    calls: list[object] = []

    async def callback(key: object) -> None:
        calls.append(key)

    debouncer = Debouncer(DELAY, callback)
    debouncer.trigger("photo-1")
    await asyncio.sleep(DELAY / 2)  # well before the first trigger would fire
    debouncer.trigger("photo-1")

    # only DELAY/2 past the *second* trigger: still pending if reset correctly
    await asyncio.sleep(DELAY / 2 + 0.01)
    assert calls == []

    await asyncio.sleep(DELAY + MARGIN)
    assert calls == ["photo-1"]


async def test_incremental_photo_indexer_reembeds_across_all_configured_providers() -> None:
    embedding_service = _FakeEmbeddingService()
    indexer = create_incremental_photo_indexer(
        embedding_service, ["clip", "other-space"], delay_seconds=DELAY
    )
    photo_id = uuid.uuid4()

    indexer.trigger(photo_id)
    await asyncio.sleep(DELAY + MARGIN)

    assert embedding_service.embed_calls == [(photo_id, "clip"), (photo_id, "other-space")]


async def test_incremental_photo_indexer_coalesces_rapid_edits_to_one_reindex() -> None:
    embedding_service = _FakeEmbeddingService()
    indexer = create_incremental_photo_indexer(embedding_service, ["clip"], delay_seconds=DELAY)
    photo_id = uuid.uuid4()

    for _ in range(10):
        indexer.trigger(photo_id)

    await asyncio.sleep(DELAY + MARGIN)

    assert embedding_service.embed_calls == [(photo_id, "clip")]
