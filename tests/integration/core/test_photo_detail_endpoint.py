import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.api.app import create_app
from core.infrastructure.ai_result_repository import AiResultRepository
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.metadata_models import Metadata
from core.infrastructure.db.plugin_models import Plugin
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.metadata_repository import MetadataRepository
from core.infrastructure.plugin_repository import PluginRepository

TOKEN = "known-token"


class _Env:
    def __init__(self, client: TestClient, photo_id: str) -> None:
        self.client = client
        self.photo_id = photo_id


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "photo_detail.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    library_root_repo = LibraryRootRepository(sessions, writer)
    photo_repo = PhotoRepository(sessions, writer)
    metadata_repo = MetadataRepository(sessions, writer)
    ai_result_repo = AiResultRepository(sessions, writer)
    plugin_repo = PluginRepository(sessions, writer)

    root = await library_root_repo.create(LibraryRoot(path="/library"))
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    photo = await photo_repo.create(
        Photo(
            library_root_id=root.id,
            relative_path="beach-sunset.jpg",
            relative_path_folded="beach-sunset.jpg",
            size_bytes=1,
            file_mtime=now,
            status="active",
            captured_at_utc=now,
        )
    )
    await metadata_repo.upsert(
        Metadata(
            photo_id=photo.id,
            camera_make="Canon",
            camera_model="EOS R5",
            width=6000,
            height=4000,
            raw_exif_blob={},
        )
    )
    await plugin_repo.upsert(
        Plugin(
            id="vit-gpt2-caption",
            name="Captioner",
            capability_types="caption",
            version="1.0.0",
            source="builtin",
            enabled=True,
        )
    )
    await ai_result_repo.record_result(
        photo_id=photo.id,
        plugin_id="vit-gpt2-caption",
        capability="caption",
        model_version="vit-gpt2-image-captioning@1",
        payload={"caption": "a dog running on the beach"},
        confidence=0.9,
    )

    app = create_app(
        token=TOKEN,
        photo_repo=photo_repo,
        metadata_repo=metadata_repo,
        ai_result_repo=ai_result_repo,
    )
    client = TestClient(app)

    try:
        yield _Env(client, str(photo.id))
    finally:
        await writer.close()
        await engine.dispose()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_photo_detail_requires_auth(env: _Env) -> None:
    response = env.client.get(f"/api/v1/photos/{env.photo_id}")

    assert response.status_code == 401


def test_photo_detail_returns_metadata_and_current_ai_results(env: _Env) -> None:
    response = env.client.get(f"/api/v1/photos/{env.photo_id}", headers=_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == env.photo_id
    assert body["relative_path"] == "beach-sunset.jpg"
    assert body["camera_make"] == "Canon"
    assert body["camera_model"] == "EOS R5"
    assert body["width"] == 6000
    assert body["height"] == 4000
    assert body["ai_results"] == [
        {
            "capability": "caption",
            "payload": {"caption": "a dog running on the beach"},
            "confidence": 0.9,
            "model_version": "vit-gpt2-image-captioning@1",
        }
    ]


def test_photo_detail_404s_for_unknown_photo(env: _Env) -> None:
    response = env.client.get(
        "/api/v1/photos/00000000-0000-0000-0000-000000000000", headers=_auth_headers()
    )

    assert response.status_code == 404


async def test_photo_detail_works_without_metadata_or_ai_results(tmp_path: Path) -> None:
    engine = create_engine(tmp_path / "bare.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    library_root_repo = LibraryRootRepository(sessions, writer)
    photo_repo = PhotoRepository(sessions, writer)
    metadata_repo = MetadataRepository(sessions, writer)
    ai_result_repo = AiResultRepository(sessions, writer)

    root = await library_root_repo.create(LibraryRoot(path="/library"))
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    photo = await photo_repo.create(
        Photo(
            library_root_id=root.id,
            relative_path="unanalyzed.jpg",
            relative_path_folded="unanalyzed.jpg",
            size_bytes=1,
            file_mtime=now,
            status="active",
        )
    )

    app = create_app(
        token=TOKEN,
        photo_repo=photo_repo,
        metadata_repo=metadata_repo,
        ai_result_repo=ai_result_repo,
    )
    client = TestClient(app)

    response = client.get(f"/api/v1/photos/{photo.id}", headers=_auth_headers())

    await writer.close()
    await engine.dispose()

    assert response.status_code == 200
    body = response.json()
    assert body["camera_make"] is None
    assert body["ai_results"] == []


def test_photo_detail_returns_503_when_not_configured() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.get(
        f"/api/v1/photos/{uuid.uuid4()}",
        headers=_auth_headers(),
    )

    assert response.status_code == 503
