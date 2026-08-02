import uuid

from sqlalchemy import func, select

from core.domain.library import FileStatus
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.repository import SqlAlchemyRepository


class LibraryRootRepository(SqlAlchemyRepository[LibraryRoot]):
    model = LibraryRoot

    async def get_by_path(self, path: str) -> LibraryRoot | None:
        async with self._read_sessions() as session:
            result = await session.execute(select(LibraryRoot).where(LibraryRoot.path == path))
            return result.scalar_one_or_none()

    async def count(self) -> int:
        async with self._read_sessions() as session:
            result = await session.execute(select(func.count()).select_from(LibraryRoot))
            return result.scalar_one()


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

    async def count_by_status(self) -> dict[str, int]:
        async with self._read_sessions() as session:
            result = await session.execute(
                select(Photo.status, func.count()).group_by(Photo.status)
            )
            return {status: count for status, count in result.all()}

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
