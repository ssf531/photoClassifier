import io
import json
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from core.domain.plugins import (
    Capability,
    ModelSource,
    PluginCompatibility,
    PluginManifest,
)
from core.domain.settings import AppSettings, SettingsPatch
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.plugin_models import Plugin
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.diagnostics_bundle import DiagnosticsBundleBuilder
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.plugin_repository import PluginRepository

_COMPATIBILITY = PluginCompatibility(core_api_version=">=1.0,<2.0")

_QUALITY_MANIFEST = PluginManifest(
    id="builtin-quality",
    name="Quality",
    version="1.0.0",
    capability=Capability.QUALITY,
    entry_point="inproc",
    runtime="python",
    model_source=ModelSource.BUNDLED,
    compatibility=_COMPATIBILITY,
)
_CAPTION_MANIFEST = PluginManifest(
    id="vit-gpt2-image-captioning",
    name="Captioning",
    version="1.0.0",
    capability=Capability.CAPTION,
    entry_point="inproc",
    runtime="python",
    model_source=ModelSource.DOWNLOAD,
    model_filename="encoder_model_quantized.onnx",
    compatibility=_COMPATIBILITY,
)


class _FakeSettingsService:
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def get(self) -> AppSettings:
        return self._settings

    async def update(self, patch: SettingsPatch) -> AppSettings:
        raise NotImplementedError


class _Env:
    def __init__(
        self,
        builder: DiagnosticsBundleBuilder,
        plugin_repo: PluginRepository,
        photo_repo: PhotoRepository,
        library_root_repo: LibraryRootRepository,
    ) -> None:
        self.builder = builder
        self.plugin_repo = plugin_repo
        self.photo_repo = photo_repo
        self.library_root_repo = library_root_repo


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "diagnostics.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    photo_repo = PhotoRepository(sessions, writer)
    library_root_repo = LibraryRootRepository(sessions, writer)
    plugin_repo = PluginRepository(sessions, writer)

    await plugin_repo.upsert(
        Plugin(
            id="builtin-quality",
            name="Quality",
            capability_types="quality",
            version="1.0.0",
            source="builtin",
            enabled=True,
        )
    )
    await plugin_repo.upsert(
        Plugin(
            id="vit-gpt2-image-captioning",
            name="Captioning",
            capability_types="caption",
            version="1.0.0",
            source="builtin",
            enabled=False,
        )
    )

    settings_service = _FakeSettingsService(
        AppSettings(library_roots=[Path("C:/Users/alice/Pictures")])
    )
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    builder = DiagnosticsBundleBuilder(
        settings_service,
        photo_repo,
        library_root_repo,
        plugin_repo,
        [_QUALITY_MANIFEST, _CAPTION_MANIFEST],
        models_dir,
        exiftool=None,
    )

    try:
        yield _Env(builder, plugin_repo, photo_repo, library_root_repo)
    finally:
        await writer.close()
        await engine.dispose()


def _read_manifest(bundle: bytes) -> dict[str, object]:
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        return json.loads(archive.read("diagnostics.json"))


async def test_bundle_contains_diagnostics_json_and_recent_log(env: _Env) -> None:
    bundle = await env.builder.build(include_paths=False)

    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert set(archive.namelist()) == {"diagnostics.json", "recent.log"}


async def test_bundle_reports_versions_and_host_details(env: _Env) -> None:
    manifest = _read_manifest(await env.builder.build(include_paths=False))

    assert manifest["core_api_version"]
    assert manifest["rawpy_version"]
    assert manifest["libraw_version"]
    assert manifest["exiftool_version"] is None  # no exiftool wired in this fixture
    assert manifest["host"]["os"]
    assert isinstance(manifest["host"]["available_execution_providers"], list)


async def test_bundle_reports_capability_status(env: _Env) -> None:
    manifest = _read_manifest(await env.builder.build(include_paths=False))

    status = manifest["capability_status"]
    assert status["quality"] == {
        "status": "available",
        "reason": None,
        "provider_id": "builtin-quality",
        "enabled": True,
    }
    assert status["caption"] == {
        "status": "unavailable",
        "reason": "model not yet acquired",
        "provider_id": "vit-gpt2-image-captioning",
        "enabled": False,
    }


async def test_bundle_reports_library_stats(env: _Env) -> None:
    root = await env.library_root_repo.create(LibraryRoot(path="C:/Pictures"))
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    await env.photo_repo.create(
        Photo(
            library_root_id=root.id,
            relative_path="a.jpg",
            relative_path_folded="a.jpg",
            size_bytes=1,
            file_mtime=now,
            status="active",
        )
    )

    manifest = _read_manifest(await env.builder.build(include_paths=False))

    assert manifest["library_stats"] == {
        "library_root_count": 1,
        "photo_count_by_status": {"active": 1},
    }


async def test_bundle_redacts_library_roots_by_default(env: _Env) -> None:
    manifest = _read_manifest(await env.builder.build(include_paths=False))

    assert manifest["settings"]["library_roots"] == ["<redacted:path>"]


async def test_bundle_includes_library_roots_with_consent(env: _Env) -> None:
    manifest = _read_manifest(await env.builder.build(include_paths=True))

    assert manifest["settings"]["library_roots"] == ["C:\\Users\\alice\\Pictures"]


async def test_bundle_redacts_paths_in_recent_log_by_default(env: _Env) -> None:
    import core.logging_setup as logging_setup
    from core.logging_setup import configure_logging, get_logger

    logging_setup._recent_log_lines.clear()
    configure_logging(json_output=True, level="INFO")
    get_logger().info("scan.discovered", path="C:\\Users\\alice\\Pictures\\a.jpg")

    bundle_without_consent = await env.builder.build(include_paths=False)
    with zipfile.ZipFile(io.BytesIO(bundle_without_consent)) as archive:
        log_text = archive.read("recent.log").decode()
    assert "alice" not in log_text

    logging_setup._recent_log_lines.clear()
