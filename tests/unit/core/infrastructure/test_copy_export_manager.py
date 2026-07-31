import shutil
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.infrastructure.change_detection import compute_content_hash
from core.infrastructure.copy_export_manager import CopyExportManager
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository

REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_JPEG = REPO_ROOT / "tests" / "fixtures" / "duplicates" / "original.jpg"


class _Env:
    def __init__(
        self,
        manager: CopyExportManager,
        photo_repo: PhotoRepository,
        library_root_path: Path,
        library_root_id: uuid.UUID,
    ) -> None:
        self.manager = manager
        self.photo_repo = photo_repo
        self.library_root_path = library_root_path
        self.library_root_id = library_root_id

    async def make_photo(self, relative_name: str, *, write_file: bool = True) -> uuid.UUID:
        if write_file:
            shutil.copyfile(FIXTURE_JPEG, self.library_root_path / relative_name)
        now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
        photo = await self.photo_repo.create(
            Photo(
                library_root_id=self.library_root_id,
                relative_path=relative_name,
                relative_path_folded=relative_name.lower(),
                size_bytes=1,
                file_mtime=now,
                status="active",
            )
        )
        return photo.id

    def source_path(self, relative_name: str) -> Path:
        return self.library_root_path / relative_name


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "copy_export.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    library_root_path = tmp_path / "library"
    library_root_path.mkdir()
    library_root_repo = LibraryRootRepository(sessions, writer)
    root = await library_root_repo.create(LibraryRoot(path=str(library_root_path)))
    photo_repo = PhotoRepository(sessions, writer)
    manager = CopyExportManager(photo_repo, library_root_repo)

    try:
        yield _Env(manager, photo_repo, library_root_path, root.id)
    finally:
        await writer.close()
        await engine.dispose()


async def test_copy_to_folder_copies_the_file_and_reports_success(
    env: _Env, tmp_path: Path
) -> None:
    photo_id = await env.make_photo("a.jpg")
    destination = tmp_path / "export"

    results = await env.manager.copy_to_folder([photo_id], str(destination))

    assert len(results) == 1
    assert results[0].success is True
    dest_path = Path(results[0].destination_path)  # type: ignore[arg-type]
    assert dest_path == destination / "a.jpg"
    assert dest_path.is_file()
    assert compute_content_hash(dest_path) == compute_content_hash(env.source_path("a.jpg"))


async def test_copy_to_folder_never_modifies_the_source(env: _Env, tmp_path: Path) -> None:
    photo_ids = [await env.make_photo(f"photo{i}.jpg") for i in range(10)]
    before_hashes = {
        photo_id: compute_content_hash(env.source_path(f"photo{i}.jpg"))
        for i, photo_id in enumerate(photo_ids)
    }
    destination = tmp_path / "export"

    results = await env.manager.copy_to_folder(photo_ids, str(destination))

    assert all(r.success for r in results)
    for i, photo_id in enumerate(photo_ids):
        assert compute_content_hash(env.source_path(f"photo{i}.jpg")) == before_hashes[photo_id]


async def test_copy_to_folder_never_overwrites_an_existing_destination_file(
    env: _Env, tmp_path: Path
) -> None:
    photo_id_a = await env.make_photo("a.jpg")
    photo_id_b = await env.make_photo("b.jpg")
    destination = tmp_path / "export"
    destination.mkdir()
    (destination / "a.jpg").write_bytes(b"an unrelated file that happens to share the name")

    results = await env.manager.copy_to_folder([photo_id_a, photo_id_b], str(destination))

    assert all(r.success for r in results)
    by_photo = {r.photo_id: r for r in results}
    assert by_photo[photo_id_a].destination_path == str(destination / "a (1).jpg")
    assert (
        destination / "a.jpg"
    ).read_bytes() == b"an unrelated file that happens to share the name"
    assert by_photo[photo_id_b].destination_path == str(destination / "b.jpg")


async def test_copy_to_folder_reports_failure_for_an_unknown_photo(
    env: _Env, tmp_path: Path
) -> None:
    results = await env.manager.copy_to_folder([uuid.uuid4()], str(tmp_path / "export"))

    assert len(results) == 1
    assert results[0].success is False


async def test_copy_to_folder_reports_failure_when_the_source_file_is_missing(
    env: _Env, tmp_path: Path
) -> None:
    photo_id = await env.make_photo("missing.jpg", write_file=False)

    results = await env.manager.copy_to_folder([photo_id], str(tmp_path / "export"))

    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error is not None
