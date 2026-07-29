from pathlib import Path

import pytest

from core.domain import settings as settings_module
from core.domain.settings import SettingsPatch
from core.infrastructure.settings_toml import TomlSettingsService


@pytest.fixture
def toml_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "config.toml"
    monkeypatch.setattr(settings_module, "config_file_path", lambda: path)
    return path


async def test_get_returns_current_settings(toml_path: Path) -> None:
    service = TomlSettingsService()

    assert service.get().log_level == "INFO"


async def test_update_persists_patch_and_returns_new_settings(toml_path: Path) -> None:
    service = TomlSettingsService()

    updated = await service.update(SettingsPatch(log_level="DEBUG"))

    assert updated.log_level == "DEBUG"
    assert service.get().log_level == "DEBUG"
    assert 'log_level = "DEBUG"' in toml_path.read_text(encoding="utf-8")


async def test_update_preserves_unrelated_existing_file_keys(toml_path: Path) -> None:
    toml_path.write_text("thumbnail_cache_max_mb = 4096\n", encoding="utf-8")
    service = TomlSettingsService()

    updated = await service.update(SettingsPatch(log_level="DEBUG"))

    assert updated.thumbnail_cache_max_mb == 4096
    assert updated.log_level == "DEBUG"
