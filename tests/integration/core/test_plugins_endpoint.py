from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.api.app import create_app
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.plugin_models import Plugin
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.plugin_repository import PluginRepository

TOKEN = "known-token"


class _Env:
    def __init__(self, client: TestClient, repo: PluginRepository) -> None:
        self.client = client
        self.repo = repo


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "plugins.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)
    repo = PluginRepository(sessions, writer)

    await repo.upsert(
        Plugin(
            id="clip",
            name="CLIP",
            capability_types="embedding,tag",
            version="1.0.0",
            source="builtin",
            enabled=True,
        )
    )
    await repo.upsert(
        Plugin(
            id="vit-gpt2-caption",
            name="Captioner",
            capability_types="caption",
            version="1.0.0",
            source="builtin",
            enabled=False,
        )
    )
    await repo.upsert(
        Plugin(
            id="remote-tagger",
            name="Remote Tagger",
            capability_types="tag",
            version="1.0.0",
            source="download",
            enabled=False,
            permissions=["network:outbound"],
        )
    )

    app = create_app(token=TOKEN, plugin_repo=repo)
    client = TestClient(app)

    try:
        yield _Env(client, repo)
    finally:
        await writer.close()
        await engine.dispose()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_list_plugins_requires_auth(env: _Env) -> None:
    response = env.client.get("/api/v1/plugins")

    assert response.status_code == 401


def test_list_plugins_returns_all_registered_plugins(env: _Env) -> None:
    response = env.client.get("/api/v1/plugins", headers=_auth_headers())

    assert response.status_code == 200
    items = {item["id"]: item for item in response.json()["items"]}
    assert items["clip"]["enabled"] is True
    assert items["vit-gpt2-caption"]["enabled"] is False
    assert items["clip"]["permissions"] == []
    assert items["remote-tagger"]["permissions"] == ["network:outbound"]


def test_update_plugin_toggles_enabled(env: _Env) -> None:
    response = env.client.patch(
        "/api/v1/plugins/vit-gpt2-caption", json={"enabled": True}, headers=_auth_headers()
    )

    assert response.status_code == 200
    assert response.json()["enabled"] is True

    follow_up = env.client.get("/api/v1/plugins", headers=_auth_headers())
    updated = next(p for p in follow_up.json()["items"] if p["id"] == "vit-gpt2-caption")
    assert updated["enabled"] is True


def test_update_plugin_404s_for_unknown_plugin(env: _Env) -> None:
    response = env.client.patch(
        "/api/v1/plugins/does-not-exist", json={"enabled": True}, headers=_auth_headers()
    )

    assert response.status_code == 404


def test_plugins_returns_503_when_not_configured() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.get("/api/v1/plugins", headers=_auth_headers())

    assert response.status_code == 503
