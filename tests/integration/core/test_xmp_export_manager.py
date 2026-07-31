import asyncio
import shutil
import uuid
from argparse import Namespace
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from core.domain.export import ExportResultItem
from core.domain.plugins import Capability
from core.infrastructure.ai_result_repository import AiResultRepository
from core.infrastructure.change_detection import compute_content_hash
from core.infrastructure.collection_repository import UserDataRepository
from core.infrastructure.db.collection_models import UserData
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.plugin_models import Plugin
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.exiftool_process import ExifToolProcess, find_exiftool
from core.infrastructure.export_repository import XmpExportRecordRepository
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.plugin_repository import PluginRepository
from core.infrastructure.xmp_export_manager import XmpExportManager

pytestmark = pytest.mark.skipif(find_exiftool() is None, reason="exiftool not installed")

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_JPEG = REPO_ROOT / "tests" / "fixtures" / "duplicates" / "original.jpg"


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.cmd_opts = Namespace(x=[f"db_path={db_path}"])
    return cfg


class _Env:
    def __init__(
        self,
        manager: XmpExportManager,
        exiftool: ExifToolProcess,
        photo_repo: PhotoRepository,
        ai_results: AiResultRepository,
        user_data: UserDataRepository,
        export_records: XmpExportRecordRepository,
        library_root_path: Path,
        library_root_id: uuid.UUID,
    ) -> None:
        self.manager = manager
        self.exiftool = exiftool
        self.photo_repo = photo_repo
        self.ai_results = ai_results
        self.user_data = user_data
        self.export_records = export_records
        self.library_root_path = library_root_path
        self.library_root_id = library_root_id

    async def make_photo(self, relative_name: str) -> uuid.UUID:
        dest = self.library_root_path / relative_name
        shutil.copyfile(FIXTURE_JPEG, dest)
        now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
        photo = await self.photo_repo.create(
            Photo(
                library_root_id=self.library_root_id,
                relative_path=relative_name,
                relative_path_folded=relative_name.lower(),
                size_bytes=dest.stat().st_size,
                file_mtime=now,
                status="active",
                content_hash=compute_content_hash(dest),
            )
        )
        return photo.id

    def photo_path(self, relative_name: str) -> Path:
        return self.library_root_path / relative_name

    def sidecar_path(self, relative_name: str) -> Path:
        return self.photo_path(relative_name).with_suffix(".xmp")


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    db_path = tmp_path / "xmp_export.db"
    await asyncio.to_thread(command.upgrade, _alembic_config(db_path), "head")

    engine = create_engine(db_path)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    library_root_path = tmp_path / "library"
    library_root_path.mkdir()

    library_root_repo = LibraryRootRepository(sessions, writer)
    root = await library_root_repo.create(LibraryRoot(path=str(library_root_path)))
    photo_repo = PhotoRepository(sessions, writer)
    ai_results = AiResultRepository(sessions, writer)
    user_data = UserDataRepository(sessions, writer)
    export_records = XmpExportRecordRepository(sessions, writer)

    plugin_repo = PluginRepository(sessions, writer)
    for plugin_id in ("clip-zero-shot-tagging", "vit-gpt2-image-captioning"):
        await plugin_repo.upsert(
            Plugin(
                id=plugin_id,
                name=plugin_id,
                capability_types="tag",
                version="1.0.0",
                source="builtin",
            )
        )

    exiftool_path = find_exiftool()
    assert exiftool_path is not None
    exiftool = ExifToolProcess(exiftool_path)
    manager = XmpExportManager(
        exiftool, photo_repo, library_root_repo, ai_results, user_data, export_records
    )

    try:
        yield _Env(
            manager,
            exiftool,
            photo_repo,
            ai_results,
            user_data,
            export_records,
            library_root_path,
            root.id,
        )
    finally:
        await exiftool.stop()
        await writer.close()
        await engine.dispose()


async def test_export_writes_caption_tags_and_rating_to_a_sidecar(env: _Env) -> None:
    photo_id = await env.make_photo("a.jpg")
    await env.ai_results.record_result(
        photo_id=photo_id,
        plugin_id="vit-gpt2-image-captioning",
        capability=Capability.CAPTION.value,
        model_version="v1",
        payload={"caption": "a dog on the beach"},
        confidence=0.9,
    )
    await env.ai_results.record_result(
        photo_id=photo_id,
        plugin_id="clip-zero-shot-tagging",
        capability=Capability.TAG.value,
        model_version="v1",
        payload={
            "tags": [{"label": "dog", "confidence": 0.8}, {"label": "beach", "confidence": 0.7}]
        },
        confidence=0.8,
    )
    await env.user_data.upsert(UserData(photo_id=photo_id, rating=4, favourite=False))

    results = await env.manager.export_xmp([photo_id])

    assert results == [ExportResultItem(photo_id=photo_id, success=True, error=None)]
    sidecar = env.sidecar_path("a.jpg")
    assert sidecar.is_file()
    written = await env.exiftool.read_metadata(sidecar)
    assert written["Description"] == "a dog on the beach"
    assert written["Rating"] == 4
    assert set(written["Subject"]) == {"dog", "beach"}


async def test_export_never_modifies_the_original_photo_file(env: _Env) -> None:
    """FEAT-081's mandatory content-hash assertion (MVP Scope Overlay,
    TASK-083): exporting must never touch the original, only its sidecar.
    """
    photo_ids = []
    for i in range(10):
        photo_id = await env.make_photo(f"photo{i}.jpg")
        await env.ai_results.record_result(
            photo_id=photo_id,
            plugin_id="vit-gpt2-image-captioning",
            capability=Capability.CAPTION.value,
            model_version="v1",
            payload={"caption": f"caption {i}"},
            confidence=0.9,
        )
        photo_ids.append(photo_id)

    before_hashes = {
        photo_id: compute_content_hash(env.photo_path(f"photo{i}.jpg"))
        for i, photo_id in enumerate(photo_ids)
    }

    results = await env.manager.export_xmp(photo_ids)

    assert all(r.success for r in results)
    for i, photo_id in enumerate(photo_ids):
        original_path = env.photo_path(f"photo{i}.jpg")
        assert compute_content_hash(original_path) == before_hashes[photo_id]
        assert env.sidecar_path(f"photo{i}.jpg").is_file()


async def test_export_creates_an_export_record(env: _Env) -> None:
    photo_id = await env.make_photo("a.jpg")
    await env.ai_results.record_result(
        photo_id=photo_id,
        plugin_id="vit-gpt2-image-captioning",
        capability=Capability.CAPTION.value,
        model_version="v1",
        payload={"caption": "hello"},
        confidence=0.9,
    )

    await env.manager.export_xmp([photo_id])

    records = await env.export_records.list(limit=10, offset=0)
    assert len(records) == 1
    assert records[0].photo_id == photo_id
    assert records[0].sidecar_path == str(env.sidecar_path("a.jpg"))


async def test_export_reports_failure_for_a_photo_with_nothing_to_export(env: _Env) -> None:
    photo_id = await env.make_photo("a.jpg")

    results = await env.manager.export_xmp([photo_id])

    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error is not None
    assert not env.sidecar_path("a.jpg").is_file()


async def test_export_reports_failure_for_an_unknown_photo(env: _Env) -> None:
    results = await env.manager.export_xmp([uuid.uuid4()])

    assert len(results) == 1
    assert results[0].success is False
