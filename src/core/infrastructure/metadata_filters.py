import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.domain.library import PhotoId
from core.domain.search import GpsBoundingBox, MetadataFilters
from core.infrastructure.db.collection_models import UserData
from core.infrastructure.db.library_models import Photo
from core.infrastructure.db.metadata_models import Metadata


async def filter_photo_ids(
    read_sessions: async_sessionmaker[AsyncSession],
    filters: MetadataFilters,
    *,
    limit: int,
    offset: int,
) -> list[PhotoId]:
    """Metadata hard filters (SDD §7.2): date range, camera model, rating
    threshold, and GPS bounding box, combined with AND semantics. Each
    filter is applied only when set, so an all-`None` `MetadataFilters`
    returns the (paginated) full photo set.
    """
    async with read_sessions() as session:
        query = (
            select(Photo.id)
            .outerjoin(Metadata, Metadata.photo_id == Photo.id)
            .outerjoin(UserData, UserData.photo_id == Photo.id)
        )

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

        query = query.order_by(Photo.id).limit(limit).offset(offset)
        result = await session.execute(query)
        return list(result.scalars().all())


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
