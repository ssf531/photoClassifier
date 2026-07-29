import tomllib
from typing import Any

import tomli_w

from core.domain import settings as settings_module
from core.domain.settings import AppSettings, SettingsPatch


class TomlSettingsService:
    def __init__(self, **cli_overrides: Any) -> None:
        self._cli_overrides = cli_overrides
        self._current = AppSettings(**self._cli_overrides)

    def get(self) -> AppSettings:
        return self._current

    async def update(self, patch: SettingsPatch) -> AppSettings:
        changes = patch.model_dump(exclude_unset=True, mode="json")
        path = settings_module.config_file_path()
        existing: dict[str, Any] = {}
        if path.is_file():
            with path.open("rb") as f:
                existing = tomllib.load(f)
        merged = {**existing, **changes}
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            tomli_w.dump(merged, f)
        self._current = AppSettings(**self._cli_overrides)
        return self._current
