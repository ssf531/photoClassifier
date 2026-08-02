import io
import json
import platform
import zipfile
from collections.abc import Sequence
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

import onnxruntime as ort
import rawpy

from core.domain.plugins import PluginManifest
from core.domain.settings import SettingsService
from core.domain.version import CORE_API_VERSION
from core.infrastructure.exiftool_process import ExifToolProcess
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.model_acquisition import compute_capability_availability
from core.infrastructure.plugin_repository import PluginRepository
from core.logging_setup import get_recent_log_lines, redact_paths_in_text

_APP_PACKAGE_NAME = "photo-intelligence-core"
_REDACTED_PATH = "<redacted:path>"


def _app_version() -> str:
    try:
        return package_version(_APP_PACKAGE_NAME)
    except PackageNotFoundError:
        return "unknown"


def _host_details() -> dict[str, object]:
    return {
        "os": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "python_version": platform.python_version(),
        "available_execution_providers": ort.get_available_providers(),
    }


class DiagnosticsBundleBuilder:
    """ "Create diagnostics bundle" (SDD §16.5): a zip a user can attach to a
    bug report, from software with no telemetry and no other route to an
    actionable report. File paths -- library roots, and any path-like
    substrings in captured log lines -- are included only when the caller
    explicitly opts in, since paths are personal data.
    """

    def __init__(
        self,
        settings_service: SettingsService,
        photo_repo: PhotoRepository,
        library_root_repo: LibraryRootRepository,
        plugin_repo: PluginRepository,
        manifests: Sequence[PluginManifest],
        models_dir: Path,
        exiftool: ExifToolProcess | None,
    ) -> None:
        self._settings_service = settings_service
        self._photo_repo = photo_repo
        self._library_root_repo = library_root_repo
        self._plugin_repo = plugin_repo
        self._manifests = manifests
        self._models_dir = models_dir
        self._exiftool = exiftool

    async def build(self, *, include_paths: bool) -> bytes:
        manifest = {
            "generated_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
            "app_version": _app_version(),
            "core_api_version": CORE_API_VERSION,
            "exiftool_version": await self._exiftool_version(),
            "rawpy_version": getattr(rawpy, "__version__", "unknown"),
            "libraw_version": ".".join(str(part) for part in getattr(rawpy, "libraw_version", ())),
            "host": _host_details(),
            "settings": self._effective_settings(include_paths=include_paths),
            "capability_status": await self._capability_status(),
            "library_stats": await self._library_stats(),
        }

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("diagnostics.json", json.dumps(manifest, indent=2, default=str))
            archive.writestr("recent.log", self._recent_logs(include_paths=include_paths))
        return buffer.getvalue()

    async def _exiftool_version(self) -> str | None:
        if self._exiftool is None:
            return None
        return await self._exiftool.version()

    def _effective_settings(self, *, include_paths: bool) -> dict[str, object]:
        data = self._settings_service.get().model_dump(mode="json")
        if not include_paths:
            data["library_roots"] = [_REDACTED_PATH for _ in data["library_roots"]]
        return data

    async def _capability_status(self) -> dict[str, dict[str, object]]:
        availability = compute_capability_availability(self._manifests, self._models_dir)
        manifests_by_capability = {manifest.capability: manifest for manifest in self._manifests}
        enabled_ids = {plugin.id for plugin in await self._plugin_repo.list_enabled()}
        return {
            capability.value: {
                "status": result.status.value,
                "reason": result.reason,
                "provider_id": manifests_by_capability[capability].id,
                "enabled": manifests_by_capability[capability].id in enabled_ids,
            }
            for capability, result in availability.items()
        }

    async def _library_stats(self) -> dict[str, object]:
        return {
            "library_root_count": await self._library_root_repo.count(),
            "photo_count_by_status": await self._photo_repo.count_by_status(),
        }

    def _recent_logs(self, *, include_paths: bool) -> str:
        text = "\n".join(get_recent_log_lines())
        if not include_paths:
            text = redact_paths_in_text(text)
        return text
