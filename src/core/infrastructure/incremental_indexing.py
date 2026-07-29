import asyncio
from collections.abc import Awaitable, Callable, Hashable, Sequence

from core.domain.library import PhotoId
from core.domain.search import EmbeddingService

DEFAULT_DEBOUNCE_SECONDS = 2.0


class Debouncer:
    """Coalesces rapid repeated triggers for the same key into a single
    delayed call (SDD §7.3): retriggering the same key before
    `delay_seconds` elapses cancels and reschedules the pending call rather
    than running it twice. Different keys never coalesce with each other.
    """

    def __init__(
        self, delay_seconds: float, callback: Callable[[Hashable], Awaitable[None]]
    ) -> None:
        self._delay_seconds = delay_seconds
        self._callback = callback
        self._pending: dict[Hashable, asyncio.Task[None]] = {}

    def trigger(self, key: Hashable) -> None:
        existing = self._pending.get(key)
        if existing is not None:
            existing.cancel()
        self._pending[key] = asyncio.create_task(self._fire_after_delay(key))

    async def _fire_after_delay(self, key: Hashable) -> None:
        try:
            await asyncio.sleep(self._delay_seconds)
        except asyncio.CancelledError:
            return
        self._pending.pop(key, None)
        await self._callback(key)


def create_incremental_photo_indexer(
    embedding_service: EmbeddingService,
    embedding_providers: Sequence[str],
    *,
    delay_seconds: float = DEFAULT_DEBOUNCE_SECONDS,
) -> Debouncer:
    """Debounced `index_photo(photo_id)` (SDD §7.3). FTS5 already stays
    current at the SQL level via triggers (TASK-032) -- no debouncing needed
    there. Vector-index updates are the one genuinely explicit, non-trigger-
    capable derived-state update SDD §7.3 calls out, so that's what this
    coalesces: re-embedding a photo across every configured embedding space
    after whatever burst of edits triggered it settles down.
    """

    async def reindex(photo_id: object) -> None:
        assert isinstance(photo_id, PhotoId)
        for provider in embedding_providers:
            await embedding_service.embed(photo_id, provider)

    return Debouncer(delay_seconds, reindex)
