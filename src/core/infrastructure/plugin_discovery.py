import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version
from pydantic import ValidationError

from core.domain.plugins import PluginManifest
from core.domain.version import CORE_API_VERSION


@dataclass(frozen=True)
class DiscoveryError:
    manifest_path: Path
    message: str


@dataclass(frozen=True)
class DiscoveryResult:
    manifests: list[PluginManifest]
    errors: list[DiscoveryError]


def check_compatibility(manifest: PluginManifest, core_version: str = CORE_API_VERSION) -> None:
    """Raise ValueError if the manifest's declared core_api_version range excludes core_version."""
    range_str = manifest.compatibility.core_api_version
    try:
        specifier = SpecifierSet(range_str)
    except InvalidSpecifier as exc:
        raise ValueError(
            f"plugin '{manifest.id}' declares an invalid core_api_version range "
            f"'{range_str}': {exc}"
        ) from exc
    if Version(core_version) not in specifier:
        raise ValueError(
            f"plugin '{manifest.id}' requires core_api_version '{range_str}', "
            f"incompatible with running core version '{core_version}'"
        )


def discover_plugins(plugins_dir: Path, core_version: str = CORE_API_VERSION) -> DiscoveryResult:
    manifests: list[PluginManifest] = []
    errors: list[DiscoveryError] = []

    if not plugins_dir.is_dir():
        return DiscoveryResult(manifests=[], errors=[])

    for manifest_path in sorted(plugins_dir.glob("*/plugin.toml")):
        try:
            manifest = _parse_manifest(manifest_path)
            check_compatibility(manifest, core_version)
            manifests.append(manifest)
        except (KeyError, ValidationError, ValueError, tomllib.TOMLDecodeError) as exc:
            errors.append(DiscoveryError(manifest_path=manifest_path, message=str(exc)))

    return DiscoveryResult(manifests=manifests, errors=errors)


def _parse_manifest(manifest_path: Path) -> PluginManifest:
    with manifest_path.open("rb") as f:
        raw: dict[str, Any] = tomllib.load(f)
    plugin_section = raw["plugin"]
    compatibility_section = raw.get("compatibility", {})
    return PluginManifest(**plugin_section, compatibility=compatibility_section)
