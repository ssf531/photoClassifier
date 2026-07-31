import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.domain.library import PhotoId
from core.domain.plugins import Capability
from core.domain.search import GpsBoundingBox, MetadataFilters
from core.infrastructure.db.ai_result_models import AiResult
from core.infrastructure.db.collection_models import UserData
from core.infrastructure.db.duplicate_models import DuplicateGroupMember
from core.infrastructure.db.library_models import Photo
from core.infrastructure.db.metadata_models import Metadata


async def filter_photo_ids(
    read_sessions: async_sessionmaker[AsyncSession],
    filters: MetadataFilters,
    *,
    limit: int,
    offset: int,
    candidate_ids: Sequence[PhotoId] | None = None,
) -> list[PhotoId]:
    """Metadata hard filters (SDD §7.2): date range, camera model, rating
    threshold, GPS bounding box, and the AI-derived `is_blurry`/
    `in_duplicate_group` predicates (TASK-080), combined with AND semantics.
    Each filter is applied only when set, so an all-`None` `MetadataFilters`
    returns the (paginated) full photo set. `candidate_ids`, when given,
    restricts to that set first -- e.g. post-filtering an already-bounded
    text/semantic result set without an unbounded intermediate fetch.
    """
    async with read_sessions() as session:
        query = (
            select(Photo.id)
            .outerjoin(Metadata, Metadata.photo_id == Photo.id)
            .outerjoin(UserData, UserData.photo_id == Photo.id)
        )

        if candidate_ids is not None:
            query = query.where(Photo.id.in_(candidate_ids))

        if filters.date_range is not None:
            if filters.date_range.start is not None:
                query = query.where(Photo.captured_at_local >= filters.date_range.start)
            if filters.date_range.end is not None:
                query = query.where(Photo.captured_at_local <= filters.date_range.end)

        if filters.camera_model is not None:
            query = query.where(Metadata.camera_model == filters.camera_model)

        if filters.min_rating is not None:
            query = query.where(UserData.rating >= filters.min_rating)

        if filters.gps_bbox is not None:
            matching_ids = await _gps_bbox_photo_ids(session, filters.gps_bbox)
            query = query.where(Photo.id.in_(matching_ids))

        if filters.is_blurry is not None:
            query = query.where(Photo.id.in_(_blurry_photo_ids_subquery(filters.is_blurry)))

        if filters.in_duplicate_group is not None:
            duplicate_ids = select(DuplicateGroupMember.photo_id)
            if filters.in_duplicate_group:
                query = query.where(Photo.id.in_(duplicate_ids))
            else:
                query = query.where(Photo.id.not_in(duplicate_ids))

        query = query.order_by(Photo.id).limit(limit).offset(offset)
        result = await session.execute(query)
        return list(result.scalars().all())


def _blurry_photo_ids_subquery(is_blurry: bool) -> Select[tuple[uuid.UUID]]:
    """A photo counts as (not-)blurry only once it's actually been analyzed:
    this matches on an existing current `quality` result, not on the
    absence of one -- there's no signal to claim "not blurry" for a photo
    that has never been scored.
    """
    return select(AiResult.photo_id).where(
        AiResult.capability == Capability.QUALITY.value,
        AiResult.is_current.is_(True),
        func.json_extract(AiResult.payload, "$.is_blurry") == (1 if is_blurry else 0),
    )


async def _gps_bbox_photo_ids(session: AsyncSession, bbox: GpsBoundingBox) -> list[uuid.UUID]:
    result = await session.execute(
        text(
            "SELECT photo_id FROM metadata_gps_rtree "
            "WHERE min_lat >= :min_lat AND max_lat <= :max_lat "
            "AND min_lon >= :min_lon AND max_lon <= :max_lon"
        ),
        {
            "min_lat": bbox.min_lat,
            "max_lat": bbox.max_lat,
            "min_lon": bbox.min_lon,
            "max_lon": bbox.max_lon,
        },
    )
    return [uuid.UUID(photo_id_str) for (photo_id_str,) in result.all()]
