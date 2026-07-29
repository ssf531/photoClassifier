import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.metadata_models import Metadata
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.metadata_repository import MetadataRepository


@pytest.fixture
async def repos(
    tmp_path: Path,
) -> AsyncIterator[tuple[MetadataRepository, PhotoRepository, LibraryRootRepository]]:
    engine = create_engine(tmp_path / "metadata.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)
    try:
        yield (
            MetadataRepository(sessions, writer),
            PhotoRepository(sessions, writer),
            LibraryRootRepository(sessions, writer),
        )
    finally:
        await writer.close()
        await engine.dispose()


async def _make_photo(
    photo_repo: PhotoRepository, library_root_repo: LibraryRootRepository, tmp_path: Path
) -> Photo:
    root = await library_root_repo.create(LibraryRoot(path=str(tmp_path)))
    return await photo_repo.create(
        Photo(
            library_root_id=root.id,
            relative_path="a.jpg",
            relative_path_folded="a.jpg",
            size_bytes=1,
            file_mtime=datetime.now(timezone.utc),  # noqa: UP017
            status="active",
        )
    )


async def test_get_by_photo_id_returns_none_when_absent(
    repos: tuple[MetadataRepository, PhotoRepository, LibraryRootRepository],
) -> None:
    metadata_repo, _, _ = repos
    assert await metadata_repo.get_by_photo_id(uuid.uuid4()) is None


async def test_upsert_creates_then_updates_same_row(
    tmp_path: Path,
    repos: tuple[MetadataRepository, PhotoRepository, LibraryRootRepository],
) -> None:
    metadata_repo, photo_repo, library_root_repo = repos
    photo = await _make_photo(photo_repo, library_root_repo, tmp_path)

    created = await metadata_repo.upsert(
        Metadata(photo_id=photo.id, camera_make="Canon", raw_exif_blob={"Make": "Canon"})
    )
    assert created.camera_make == "Canon"

    updated = await metadata_repo.upsert(
        Metadata(photo_id=photo.id, camera_make="Nikon", raw_exif_blob={"Make": "Nikon"})
    )
    assert updated.camera_make == "Nikon"

    fetched = await metadata_repo.get_by_photo_id(photo.id)
    assert fetched is not None
    assert fetched.camera_make == "Nikon"
