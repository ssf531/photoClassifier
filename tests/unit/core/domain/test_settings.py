from pathlib import Path

import pytest
from pydantic import ValidationError

from core.domain import settings as settings_module
from core.domain.settings import AppSettings


@pytest.fixture
def toml_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "config.toml"
    monkeypatch.setattr(settings_module, "config_file_path", lambda: path)
    return path


def test_defaults_apply_when_nothing_is_set(toml_path: Path) -> None:
    settings = AppSettings()

    assert settings.log_level == "INFO"
    assert settings.thumbnail_cache_max_mb == 2048
    assert settings.library_roots == []


def test_toml_file_overrides_defaults(toml_path: Path) -> None:
    toml_path.write_text('log_level = "DEBUG"\n', encoding="utf-8")

    settings = AppSettings()

    assert settings.log_level == "DEBUG"


def test_env_var_overrides_toml_file(toml_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    toml_path.write_text('log_level = "DEBUG"\n', encoding="utf-8")
    monkeypatch.setenv("PHOTO_INTELLIGENCE_LOG_LEVEL", "WARNING")

    settings = AppSettings()

    assert settings.log_level == "WARNING"


def test_cli_override_wins_over_everything(
    toml_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    toml_path.write_text('log_level = "DEBUG"\n', encoding="utf-8")
    monkeypatch.setenv("PHOTO_INTELLIGENCE_LOG_LEVEL", "WARNING")

    settings = AppSettings(log_level="ERROR")

    assert settings.log_level == "ERROR"


def test_invalid_type_in_toml_raises_validation_error_at_load_time(
    toml_path: Path,
) -> None:
    toml_path.write_text('thumbnail_cache_max_mb = "not-a-number"\n', encoding="utf-8")

    with pytest.raises(ValidationError):
        AppSettings()


def test_is_portable_reads_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(settings_module.PORTABLE_ENV_VAR, raising=False)
    assert settings_module.is_portable() is False

    monkeypatch.setenv(settings_module.PORTABLE_ENV_VAR, "true")
    assert settings_module.is_portable() is True
