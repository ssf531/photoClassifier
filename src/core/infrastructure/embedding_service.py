from collections.abc import Mapping
from pathlib import Path

from core.domain.library import PhotoId
from core.domain.providers import EmbeddingProvider, ImageRef, Vector
from core.domain.search import EmbeddingIndex, ScoredPhoto
from core.infrastructure.ai_result_repository import EmbeddingRefRepository
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository


class PhotoNotFoundError(Exception):
    pass


class UnknownEmbeddingProviderError(Exception):
    pass


class PhotoNotEmbeddedError(Exception):
    pass


def _vector_key(photo_id: PhotoId, provider: str) -> str:
    return f"{photo_id}:{provider}"


class DefaultEmbeddingService:
    """Embedding generation + storage/query (SDD §4.5), kept separate from
    the general Analysis Pipeline because embeddings have a distinct query
    pattern (ANN similarity via `EmbeddingIndex`) from other AI results.

    `similar_to()` has no `provider` parameter in its SDD-specified
    signature, so it uses `default_provider` -- the only ambiguity v1 has to
    resolve, since v1 ships exactly one embedding space (CLIP).
    """

    def __init__(
        self,
        providers: Mapping[str, EmbeddingProvider],
        index: EmbeddingIndex,
        embedding_refs: EmbeddingRefRepository,
        photo_repo: PhotoRepository,
        library_root_repo: LibraryRootRepository,
        default_provider: str,
    ) -> None:
        self._providers = providers
        self._index = index
        self._embedding_refs = embedding_refs
        self._photo_repo = photo_repo
        self._library_root_repo = library_root_repo
        self._default_provider = default_provider

    async def embed(self, photo_id: PhotoId, provider: str) -> None:
        provider_impl = self._resolve_provider(provider)
        image = await self._image_ref_for(photo_id)

        vector = await provider_impl.embed_image(image)
        vector_key = _vector_key(photo_id, provider)
        await self._index.upsert(
            vector_key=vector_key, vector_space=provider, photo_id=photo_id, vector=vector
        )
        await self._embedding_refs.upsert_embedding(
            photo_id=photo_id,
            plugin_id=provider_impl.provider_id,
            model_version=provider_impl.model_version,
            vector_space=provider,
            vector_key=vector_key,
        )

    async def similar_to(self, photo_id: PhotoId, k: int) -> list[ScoredPhoto]:
        vector_key = _vector_key(photo_id, self._default_provider)
        vector = await self._index.get(vector_key)
        if vector is None:
            raise PhotoNotEmbeddedError(str(photo_id))

        # over-fetch by one: the photo always matches its own vector exactly
        hits = await self._index.query(vector, vector_space=self._default_provider, limit=k + 1)
        return [
            ScoredPhoto(photo_id=hit.photo_id, score=hit.score)
            for hit in hits
            if hit.photo_id != photo_id
        ][:k]

    async def embed_text(self, query: str, provider: str) -> Vector:
        provider_impl = self._resolve_provider(provider)
        return await provider_impl.embed_text(query)

    def _resolve_provider(self, provider: str) -> EmbeddingProvider:
        try:
            return self._providers[provider]
        except KeyError:
            raise UnknownEmbeddingProviderError(provider) from None

    async def _image_ref_for(self, photo_id: PhotoId) -> ImageRef:
        photo = await self._photo_repo.get(photo_id)
        if photo is None:
            raise PhotoNotFoundError(str(photo_id))
        root = await self._library_root_repo.get(photo.library_root_id)
        if root is None:
            raise PhotoNotFoundError(str(photo_id))
        return ImageRef(photo_id=photo_id, path=Path(root.path) / photo.relative_path)
