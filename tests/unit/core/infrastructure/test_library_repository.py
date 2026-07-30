from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from core.domain.library import FileStatus
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository


def _photo(
    library_root_id: object,
    relative_path: str,
    status: FileStatus = FileStatus.ACTIVE,
    captured_at_utc: datetime | None = None,
) -> Photo:
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    return Photo(
        library_root_id=library_root_id,
        relative_path=relative_path,
        relative_path_folded=relative_path.lower(),
        size_bytes=1024,
        file_mtime=now,
        status=status.value,
        captured_at_utc=captured_at_utc,
    )


@pytest.fixture
async def repos(
    tmp_path: Path,
) -> AsyncIterator[tuple[LibraryRootRepository, PhotoRepository]]:
    engine = create_engine(tmp_path / "library.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)
    try:
        yield LibraryRootRepository(sessions, writer), PhotoRepository(sessions, writer)
    finally:
        await writer.close()
        await engine.dispose()


async def test_photo_unique_constraint_on_root_and_folded_path(
    repos: tuple[LibraryRootRepository, PhotoRepository],
) -> None:
    root_repo, photo_repo = repos
    root = await root_repo.create(LibraryRoot(path="C:/Pictures"))

    await photo_repo.create(_photo(root.id, "Vacation/IMG_0001.JPG"))

    with pytest.raises(IntegrityError):
        await photo_repo.create(_photo(root.id, "vacation/img_0001.jpg"))


async def test_list_by_status_filters_and_paginates(
    repos: tuple[LibraryRootRepository, PhotoRepository],
) -> None:
    root_repo, photo_repo = repos
    root = await root_repo.create(LibraryRoot(path="C:/Pictures"))

    for i in range(3):
        await photo_repo.create(_photo(root.id, f"active-{i}.jpg", FileStatus.ACTIVE))
    await photo_repo.create(_photo(root.id, "missing-0.jpg", FileStatus.MISSING))

    active = await photo_repo.list_by_status(FileStatus.ACTIVE, limit=10, offset=0)
    missing = await photo_repo.list_by_status(FileStatus.MISSING, limit=10, offset=0)
    first_page = await photo_repo.list_by_status(FileStatus.ACTIVE, limit=2, offset=0)

    assert len(active) == 3
    assert len(missing) == 1
    assert len(first_page) == 2


async def test_list_active_for_grid_orders_newest_first_and_excludes_non_active(
    repos: tuple[LibraryRootRepository, PhotoRepository],
) -> None:
    root_repo, photo_repo = repos
    root = await root_repo.create(LibraryRoot(path="C:/Pictures"))
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration

    oldest = await photo_repo.create(
        _photo(root.id, "oldest.jpg", captured_at_utc=now - timedelta(days=2))
    )
    newest = await photo_repo.create(
        _photo(root.id, "newest.jpg", captured_at_utc=now - timedelta(days=0))
    )
    middle = await photo_repo.create(
        _photo(root.id, "middle.jpg", captured_at_utc=now - timedelta(days=1))
    )
    await photo_repo.create(_photo(root.id, "missing.jpg", FileStatus.MISSING, now))

    page = await photo_repo.list_active_for_grid(limit=10, offset=0)

    assert [p.id for p in page] == [newest.id, middle.id, oldest.id]


async def test_list_active_for_grid_paginates(
    repos: tuple[LibraryRootRepository, PhotoRepository],
) -> None:
    root_repo, photo_repo = repos
    root = await root_repo.create(LibraryRoot(path="C:/Pictures"))
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration

    for i in range(5):
        await photo_repo.create(
            _photo(root.id, f"photo-{i}.jpg", captured_at_utc=now - timedelta(days=i))
        )

    first_page = await photo_repo.list_active_for_grid(limit=2, offset=0)
    second_page = await photo_repo.list_active_for_grid(limit=2, offset=2)

    assert [p.relative_path for p in first_page] == ["photo-0.jpg", "photo-1.jpg"]
    assert [p.relative_path for p in second_page] == ["photo-2.jpg", "photo-3.jpg"]
