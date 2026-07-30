import sqlite3
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.composition import Composition, compose
from core.domain import settings as settings_module
from core.infrastructure.thumbnail_service import ThumbnailService

_BUILTIN_PLUGIN_IDS = {
    "clip-vit-base-patch32",
    "vit-gpt2-image-captioning",
    "clip-zero-shot-tagging",
    "builtin-quality",
    "builtin-duplicate-detection",
}


def _table_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {row[0] for row in rows}


def _auth_headers(composition: Composition) -> dict[str, str]:
    return {"Authorization": f"Bearer {composition.app.state.launch_token}"}


@pytest.fixture
async def composition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Composition]:
    # Portable mode pins data_dir()/config_dir() to a path derived from
    # sys.argv[0] (see core.domain.settings), which is the one mechanism that
    # redirects every module-level `data_dir()` reference consistently --
    # composition.py and settings.py each hold their own imported binding of
    # the function, so patching either module's attribute directly would miss
    # the other.
    monkeypatch.setenv(settings_module.PORTABLE_ENV_VAR, "true")
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "core.exe")])
    yield await compose()


def test_compose_migrates_a_fresh_database_to_head(
    composition: Composition, tmp_path: Path
) -> None:
    db_path = tmp_path / "data" / "photo-intelligence.db"

    assert db_path.is_file()
    assert {"library_root", "photo", "plugin", "job", "job_item"} <= _table_names(db_path)


def test_compose_wires_a_working_thumbnail_service(composition: Composition) -> None:
    assert isinstance(composition.app.state.thumbnail_service, ThumbnailService)

    client = TestClient(composition.app)
    response = client.get(
        "/api/v1/thumbnails/00000000-0000-0000-0000-000000000000?size=grid",
        headers=_auth_headers(composition),
    )

    # A 503 would mean the service is still unconfigured; 404 proves it ran
    # and simply couldn't find this (nonexistent) photo.
    assert response.status_code == 404


def test_compose_registers_builtin_plugins_disabled_by_default(composition: Composition) -> None:
    client = TestClient(composition.app)

    response = client.get("/api/v1/plugins", headers=_auth_headers(composition))

    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["id"] for item in items} == _BUILTIN_PLUGIN_IDS
    assert all(item["source"] == "builtin" for item in items)
    assert all(item["enabled"] is False for item in items)


async def test_compose_is_idempotent_across_repeated_calls(composition: Composition) -> None:
    # A second `compose()` against the same data dir (e.g. app restart) must
    # not fail re-running migrations or re-discovering plugins, and must not
    # duplicate the builtin plugin rows.
    second = await compose()

    client = TestClient(second.app)
    response = client.get("/api/v1/plugins", headers=_auth_headers(second))

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert len(ids) == len(_BUILTIN_PLUGIN_IDS)
    assert set(ids) == _BUILTIN_PLUGIN_IDS
