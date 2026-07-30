import os
import sys
from pathlib import Path
from typing import Protocol

import platformdirs
from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

APP_NAME = "photo-intelligence"
ENV_PREFIX = "PHOTO_INTELLIGENCE_"
PORTABLE_ENV_VAR = f"{ENV_PREFIX}PORTABLE"


def is_portable() -> bool:
    return os.environ.get(PORTABLE_ENV_VAR, "").strip().lower() in {"1", "true", "yes"}


def _portable_base_dir() -> Path:
    return Path(sys.argv[0]).resolve().parent / "data"


def config_dir() -> Path:
    if is_portable():
        return _portable_base_dir()
    return Path(platformdirs.user_config_dir(APP_NAME, appauthor=False))


def data_dir() -> Path:
    if is_portable():
        return _portable_base_dir()
    return Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))


def models_dir() -> Path:
    """Local model-weights cache (SDD §6.4/§16.4), under the platform data
    directory so it moves with `--portable` like everything else."""
    return data_dir() / "models"


def thumbnails_dir() -> Path:
    """On-disk thumbnail cache (SDD §12), under the platform data directory
    so it moves with `--portable` like everything else."""
    return data_dir() / "thumbnails"


def config_file_path() -> Path:
    return config_dir() / "config.toml"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, extra="ignore")

    library_roots: list[Path] = Field(default_factory=list)
    log_level: str = "INFO"
    thumbnail_cache_max_mb: int = 2048
    gpu_execution_provider: str | None = None
    missing_photo_grace_period_days: int = 30
    thumbnail_grid_size_px: int = 256
    thumbnail_preview_size_px: int = 1024

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        toml_source = TomlConfigSettingsSource(settings_cls, toml_file=config_file_path())
        return (init_settings, env_settings, toml_source)


class SettingsPatch(BaseModel):
    library_roots: list[Path] | None = None
    log_level: str | None = None
    thumbnail_cache_max_mb: int | None = None
    gpu_execution_provider: str | None = None
    missing_photo_grace_period_days: int | None = None
    thumbnail_grid_size_px: int | None = None
    thumbnail_preview_size_px: int | None = None


class SettingsService(Protocol):
    def get(self) -> AppSettings: ...
    async def update(self, patch: SettingsPatch) -> AppSettings: ...
