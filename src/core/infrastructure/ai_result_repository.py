import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.infrastructure.db.ai_result_models import AiResult, EmbeddingRef
from core.infrastructure.db.repository import SqlAlchemyRepository


class AiResultRepository(SqlAlchemyRepository[AiResult]):
    model = AiResult

    async def list_current_by_photo(self, photo_id: uuid.UUID) -> list[AiResult]:
        async with self._read_sessions() as session:
            result = await session.execute(
                select(AiResult)
                .where(AiResult.photo_id == photo_id, AiResult.is_current.is_(True))
                .order_by(AiResult.id)
            )
            return list(result.scalars().all())

    async def record_result(
        self,
        *,
        photo_id: uuid.UUID,
        plugin_id: str,
        capability: str,
        model_version: str,
        payload: dict[str, Any],
        confidence: float,
    ) -> AiResult:
        """Insert a new result and flip the prior current row (same photo,
        plugin, and capability) to `is_current=False`, atomically (SDD §5.4).
        A different plugin_id producing the same capability keeps its own
        independent current row -- see SDD §6.6, multi-provider coexistence.
        """
        async with self._writer.transaction() as connection:
            session = AsyncSession(bind=connection, expire_on_commit=False)
            await session.execute(
                update(AiResult)
                .where(
                    AiResult.photo_id == photo_id,
                    AiResult.plugin_id == plugin_id,
                    AiResult.capability == capability,
                    AiResult.is_current.is_(True),
                )
                .values(is_current=False)
            )
            new_result = AiResult(
                photo_id=photo_id,
                plugin_id=plugin_id,
                capability=capability,
                model_version=model_version,
                payload=payload,
                confidence=confidence,
                is_current=True,
            )
            session.add(new_result)
            await session.flush()
            await session.refresh(new_result)
            return new_result


class EmbeddingRefRepository(SqlAlchemyRepository[EmbeddingRef]):
    model = EmbeddingRef

    async def upsert_embedding(
        self,
        *,
        photo_id: uuid.UUID,
        plugin_id: str,
        model_version: str,
        vector_space: str,
        vector_key: str,
    ) -> EmbeddingRef:
        """Embeddings have no history to preserve (unlike `ai_result`): a new
        vector for the same (photo, plugin, vector_space) simply replaces the
        old one, since a superseded embedding has no comparison value.
        """
        async with self._writer.transaction() as connection:
            session = AsyncSession(bind=connection, expire_on_commit=False)
            result = await session.execute(
                select(EmbeddingRef).where(
                    EmbeddingRef.photo_id == photo_id,
                    EmbeddingRef.plugin_id == plugin_id,
                    EmbeddingRef.vector_space == vector_space,
                )
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                existing.model_version = model_version
                existing.vector_key = vector_key
                await session.flush()
                await session.refresh(existing)
                return existing

            created = EmbeddingRef(
                photo_id=photo_id,
                plugin_id=plugin_id,
                model_version=model_version,
                vector_space=vector_space,
                vector_key=vector_key,
            )
            session.add(created)
            await session.flush()
            await session.refresh(created)
            return created
