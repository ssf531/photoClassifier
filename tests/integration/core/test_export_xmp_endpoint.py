import asyncio
import uuid
from argparse import Namespace
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command
from core.api.app import create_app
from core.domain.export import ExportResultItem
from core.domain.providers import Vector
from core.domain.search import ScoredPhoto
from core.infrastructure.collection_manager import CollectionManager
from core.infrastructure.collection_repository import (
    CollectionItemRepository,
    CollectionRepository,
    SmartCollectionRuleRepository,
)
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.export_presets import DEFAULT_PRESET, ExportPreset
from core.infrastructure.fts_search_index import FtsTextSearchIndex
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.search_service import DefaultSearchService
from core.infrastructure.vec_embedding_index import SqliteVecEmbeddingIndex

TOKEN = "known-token"
REPO_ROOT = Path(__file__).resolve().parents[3]


class _FakeXmpExportManager:
    """A real `ExifToolProcess`-backed manager can't be exercised through
    `TestClient`: its subprocess transport is bound to whichever event loop
    first uses it, and `TestClient` runs the ASGI app on a separate loop/
    thread (an anyio blocking portal) than an async pytest fixture's --
    the resulting cross-loop read raises `RuntimeError: ... attached to a
    different loop`. The real subprocess behavior (writing/creating
    sidecars, never touching originals) is already covered directly,
    without TestClient, in test_xmp_export_manager.py; this fake verifies
    only the endpoint's own request/response wiring.
    """

    def __init__(self) -> None:
        self.received_photo_ids: list[uuid.UUID] = []
        self.received_preset: ExportPreset | None = None

    async def export_xmp(
        self, photo_ids: list[uuid.UUID], preset: ExportPreset = DEFAULT_PRESET
    ) -> list[ExportResultItem]:
        self.received_photo_ids = list(photo_ids)
        self.received_preset = preset
        return [ExportResultItem(photo_id=photo_id, success=True) for photo_id in photo_ids]


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_export_xmp_requires_auth() -> None:
    app = create_app(token=TOKEN, xmp_export_manager=_FakeXmpExportManager())
    client = TestClient(app)
    photo_id = str(uuid.uuid4())

    response = client.post("/api/v1/export/xmp", json={"photo_ids": [photo_id]})

    assert response.status_code == 401


def test_export_xmp_passes_photo_ids_through_and_reports_the_result() -> None:
    manager = _FakeXmpExportManager()
    app = create_app(token=TOKEN, xmp_export_manager=manager)
    client = TestClient(app)
    photo_id = str(uuid.uuid4())

    response = client.post(
        "/api/v1/export/xmp",
        json={"photo_ids": [photo_id]},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["items"] == [{"photo_id": photo_id, "success": True, "error": None}]
    assert manager.received_photo_ids == [uuid.UUID(photo_id)]
    assert manager.received_preset is not None
    assert manager.received_preset.name == "default"


def test_export_xmp_passes_the_requested_preset_through() -> None:
    manager = _FakeXmpExportManager()
    app = create_app(token=TOKEN, xmp_export_manager=manager)
    client = TestClient(app)
    photo_id = str(uuid.uuid4())

    response = client.post(
        "/api/v1/export/xmp",
        json={"photo_ids": [photo_id], "preset": "lightroom"},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert manager.received_preset is not None
    assert manager.received_preset.name == "lightroom"


def test_export_xmp_returns_422_for_an_unknown_preset() -> None:
    app = create_app(token=TOKEN, xmp_export_manager=_FakeXmpExportManager())
    client = TestClient(app)

    response = client.post(
        "/api/v1/export/xmp",
        json={"photo_ids": [str(uuid.uuid4())], "preset": "nonexistent"},
        headers=_auth_headers(),
    )

    assert response.status_code == 422


def test_export_xmp_returns_503_when_not_configured() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.post("/api/v1/export/xmp", json={"photo_ids": []}, headers=_auth_headers())

    assert response.status_code == 503


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.cmd_opts = Namespace(x=[f"db_path={db_path}"])
    return cfg


class _UnusedEmbeddingService:
    """These tests only ever exercise a virtual collection's membership,
    never a smart collection's saved-query evaluation, so `SearchService`'s
    embedding path is never called."""

    async def embed(self, photo_id: uuid.UUID, provider: str) -> None:
        raise NotImplementedError

    async def similar_to(self, photo_id: uuid.UUID, k: int) -> list[ScoredPhoto]:
        raise NotImplementedError

    async def embed_text(self, query: str, provider: str) -> Vector:
        raise NotImplementedError


class _CollectionExportEnv:
    def __init__(
        self, client: TestClient, xmp_export_manager: _FakeXmpExportManager, collection_id: str
    ) -> None:
        self.client = client
        self.xmp_export_manager = xmp_export_manager
        self.collection_id = collection_id


@pytest.fixture
async def collection_export_env(tmp_path: Path) -> AsyncIterator[_CollectionExportEnv]:
    db_path = tmp_path / "collection_export.db"
    await asyncio.to_thread(command.upgrade, _alembic_config(db_path), "head")

    engine = create_engine(db_path)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    library_root_repo = LibraryRootRepository(sessions, writer)
    photo_repo = PhotoRepository(sessions, writer)
    root = await library_root_repo.create(LibraryRoot(path="/library"))
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    photo_ids = []
    for i in range(3):
        photo = await photo_repo.create(
            Photo(
                library_root_id=root.id,
                relative_path=f"{i}.jpg",
                relative_path_folded=f"{i}.jpg",
                size_bytes=1,
                file_mtime=now,
                status="active",
            )
        )
        photo_ids.append(photo.id)

    search_service = DefaultSearchService(
        text_index=FtsTextSearchIndex(sessions),
        embedding_index=SqliteVecEmbeddingIndex(sessions, writer),
        embedding_service=_UnusedEmbeddingService(),
        read_sessions=sessions,
        default_embedding_provider="clip",
    )
    collection_manager = CollectionManager(
        CollectionRepository(sessions, writer),
        CollectionItemRepository(sessions, writer),
        SmartCollectionRuleRepository(sessions, writer),
        search_service,
    )
    collection = await collection_manager.create("Trip")
    await collection_manager.add_members(collection.id, photo_ids)

    xmp_export_manager = _FakeXmpExportManager()
    app = create_app(
        token=TOKEN, collection_manager=collection_manager, xmp_export_manager=xmp_export_manager
    )
    client = TestClient(app)

    try:
        yield _CollectionExportEnv(client, xmp_export_manager, str(collection.id))
    finally:
        await writer.close()
        await engine.dispose()


def test_export_collection_xmp_requires_auth(collection_export_env: _CollectionExportEnv) -> None:
    response = collection_export_env.client.post(
        f"/api/v1/collections/{collection_export_env.collection_id}/export/xmp", json={}
    )

    assert response.status_code == 401


def test_export_collection_xmp_exports_every_member(
    collection_export_env: _CollectionExportEnv,
) -> None:
    response = collection_export_env.client.post(
        f"/api/v1/collections/{collection_export_env.collection_id}/export/xmp",
        json={},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 3
    assert len(collection_export_env.xmp_export_manager.received_photo_ids) == 3
    assert collection_export_env.xmp_export_manager.received_preset is not None
    assert collection_export_env.xmp_export_manager.received_preset.name == "default"


def test_export_collection_xmp_passes_the_requested_preset_through(
    collection_export_env: _CollectionExportEnv,
) -> None:
    response = collection_export_env.client.post(
        f"/api/v1/collections/{collection_export_env.collection_id}/export/xmp",
        json={"preset": "lightroom"},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert collection_export_env.xmp_export_manager.received_preset is not None
    assert collection_export_env.xmp_export_manager.received_preset.name == "lightroom"


def test_export_collection_xmp_returns_404_for_an_unknown_collection(
    collection_export_env: _CollectionExportEnv,
) -> None:
    response = collection_export_env.client.post(
        "/api/v1/collections/00000000-0000-0000-0000-000000000000/export/xmp",
        json={},
        headers=_auth_headers(),
    )

    assert response.status_code == 404


def test_export_collection_xmp_returns_422_for_an_unknown_preset(
    collection_export_env: _CollectionExportEnv,
) -> None:
    response = collection_export_env.client.post(
        f"/api/v1/collections/{collection_export_env.collection_id}/export/xmp",
        json={"preset": "nonexistent"},
        headers=_auth_headers(),
    )

    assert response.status_code == 422


def test_export_collection_xmp_returns_503_when_not_configured() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.post(
        "/api/v1/collections/00000000-0000-0000-0000-000000000000/export/xmp",
        json={},
        headers=_auth_headers(),
    )

    assert response.status_code == 503
