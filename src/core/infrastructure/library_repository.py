import uuid

from sqlalchemy import select

from core.domain.library import FileStatus
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.repository import SqlAlchemyRepository


class LibraryRootRepository(SqlAlchemyRepository[LibraryRoot]):
    model = LibraryRoot


class PhotoRepository(SqlAlchemyRepository[Photo]):
    model = Photo

    async def list_by_status(self, status: FileStatus, *, limit: int, offset: int) -> list[Photo]:
        async with self._read_sessions() as session:
            result = await session.execute(
                select(Photo)
                .where(Photo.status == status.value)
                .order_by(Photo.id)
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    async def list_by_library_root(
        self, library_root_id: uuid.UUID, *, limit: int, offset: int
    ) -> list[Photo]:
        async with self._read_sessions() as session:
            result = await session.execute(
                select(Photo)
                .where(Photo.library_root_id == library_root_id)
                .order_by(Photo.id)
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    async def list_active_for_grid(self, *, limit: int, offset: int) -> list[Photo]:
        """Newest-first paging for the Browse UI grid (TASK-065). `id` is a
        secondary sort key purely to make paging stable for photos sharing a
        `captured_at_utc` (including the common all-NULL case), not for any
        meaning of its own.
        """
        async with self._read_sessions() as session:
            result = await session.execute(
                select(Photo)
                .where(Photo.status == FileStatus.ACTIVE.value)
                .order_by(Photo.captured_at_utc.desc(), Photo.id)
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())
