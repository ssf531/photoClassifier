from pathlib import Path

import pytest

from core.domain.plugins import Capability, ModelSource, PluginCompatibility, PluginManifest
from core.infrastructure.plugin_discovery import check_compatibility, discover_plugins

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "plugins"


def _manifest(core_api_version: str) -> PluginManifest:
    return PluginManifest(
        id="test-plugin",
        name="Test Plugin",
        version="1.0.0",
        capability=Capability.TAG,
        entry_point="inproc",
        runtime="python",
        model_source=ModelSource.BUNDLED,
        compatibility=PluginCompatibility(core_api_version=core_api_version),
    )


def test_check_compatibility_accepts_matching_range() -> None:
    check_compatibility(_manifest(">=1.0,<2.0"), core_version="1.0.0")


def test_check_compatibility_rejects_excluded_range() -> None:
    with pytest.raises(ValueError, match="incompatible"):
        check_compatibility(_manifest(">=2.0,<3.0"), core_version="1.0.0")


def test_check_compatibility_rejects_invalid_range_string() -> None:
    with pytest.raises(ValueError, match="invalid core_api_version range"):
        check_compatibility(_manifest("not-a-valid-range"), core_version="1.0.0")


def test_discovers_all_fixture_plugin_directories() -> None:
    result = discover_plugins(FIXTURES_DIR)

    assert len(result.manifests) == 1
    assert len(result.errors) == 3


def test_valid_manifest_is_parsed_correctly() -> None:
    result = discover_plugins(FIXTURES_DIR)

    (manifest,) = result.manifests
    assert manifest.id == "onnx-clip-embedding"
    assert manifest.capability == Capability.EMBEDDING
    assert manifest.entry_point == "inproc"
    assert manifest.compatibility.core_api_version == ">=1.0,<2.0"


def test_missing_required_field_is_rejected_with_specific_error() -> None:
    result = discover_plugins(FIXTURES_DIR)

    error = next(e for e in result.errors if "missing_field_plugin" in str(e.manifest_path))
    assert "version" in error.message


def test_bad_capability_enum_value_is_rejected_with_specific_error() -> None:
    result = discover_plugins(FIXTURES_DIR)

    error = next(e for e in result.errors if "bad_capability_plugin" in str(e.manifest_path))
    assert "capability" in error.message


def test_incompatible_core_api_version_is_rejected_naming_the_mismatch() -> None:
    result = discover_plugins(FIXTURES_DIR)

    error = next(e for e in result.errors if "incompatible_version_plugin" in str(e.manifest_path))
    assert "future-plugin" in error.message
    assert ">=99.0,<100.0" in error.message
    assert "1.0.0" in error.message


def test_missing_plugins_directory_returns_empty_result(tmp_path: Path) -> None:
    result = discover_plugins(tmp_path / "does-not-exist")

    assert result.manifests == []
    assert result.errors == []
