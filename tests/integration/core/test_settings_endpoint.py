from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.api.app import create_app
from core.domain import settings as settings_module
from core.infrastructure.settings_toml import TomlSettingsService

TOKEN = "known-token"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings_module, "config_file_path", lambda: tmp_path / "config.toml")
    service = TomlSettingsService()
    app = create_app(token=TOKEN, settings_service=service)
    return TestClient(app)


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_get_settings_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/settings")

    assert response.status_code == 401


def test_get_settings_returns_current_settings(client: TestClient) -> None:
    response = client.get("/api/v1/settings", headers=_auth_headers())

    assert response.status_code == 200
    assert response.json()["log_level"] == "INFO"


def test_patch_settings_updates_and_persists(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/settings", json={"log_level": "DEBUG"}, headers=_auth_headers()
    )

    assert response.status_code == 200
    assert response.json()["log_level"] == "DEBUG"

    follow_up = client.get("/api/v1/settings", headers=_auth_headers())
    assert follow_up.json()["log_level"] == "DEBUG"


def test_settings_returns_503_when_not_configured() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.get("/api/v1/settings", headers=_auth_headers())

    assert response.status_code == 503
