from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.api.app import create_app
from core.domain.plugins import Capability
from core.infrastructure.ai_result_repository import AiResultRepository
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.plugin_models import Plugin
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.duplicate_repository import DuplicateGroupMemberRepository
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.plugin_repository import PluginRepository
from core.infrastructure.recommendation_engine import RecommendationEngine

TOKEN = "known-token"


class _Env:
    def __init__(self, client: TestClient, screenshot_photo_id: str) -> None:
        self.client = client
        self.screenshot_photo_id = screenshot_photo_id


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "recommendations.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    library_root_repo = LibraryRootRepository(sessions, writer)
    photo_repo = PhotoRepository(sessions, writer)
    ai_results = AiResultRepository(sessions, writer)
    root = await library_root_repo.create(LibraryRoot(path="/library"))
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    photo = await photo_repo.create(
        Photo(
            library_root_id=root.id,
            relative_path="a.jpg",
            relative_path_folded="a.jpg",
            size_bytes=1,
            file_mtime=now,
            status="active",
        )
    )
    plugin_repo = PluginRepository(sessions, writer)
    await plugin_repo.upsert(
        Plugin(
            id="clip-zero-shot-tagging",
            name="clip-zero-shot-tagging",
            capability_types="tag",
            version="1.0.0",
            source="builtin",
        )
    )
    await ai_results.record_result(
        photo_id=photo.id,
        plugin_id="clip-zero-shot-tagging",
        capability=Capability.TAG.value,
        model_version="v1",
        payload={"tags": [{"label": "screenshot", "confidence": 0.9}]},
        confidence=0.9,
    )

    recommendation_engine = RecommendationEngine(
        ai_results, DuplicateGroupMemberRepository(sessions, writer)
    )
    app = create_app(token=TOKEN, recommendation_engine=recommendation_engine)
    client = TestClient(app)

    try:
        yield _Env(client, str(photo.id))
    finally:
        await writer.close()
        await engine.dispose()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_list_recommendations_requires_auth(env: _Env) -> None:
    response = env.client.get("/api/v1/recommendations")

    assert response.status_code == 401


def test_list_recommendations_groups_photos_by_category(env: _Env) -> None:
    response = env.client.get("/api/v1/recommendations", headers=_auth_headers())

    assert response.status_code == 200
    items = {item["category"]: item["photo_ids"] for item in response.json()["items"]}
    assert items["screenshots"] == [env.screenshot_photo_id]
    assert items["low_quality"] == []
    assert items["near_duplicates"] == []


def test_list_recommendations_returns_503_when_not_configured() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.get("/api/v1/recommendations", headers=_auth_headers())

    assert response.status_code == 503
