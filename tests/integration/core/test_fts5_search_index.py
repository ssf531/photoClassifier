import asyncio
from argparse import Namespace
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import command
from core.infrastructure.ai_result_repository import AiResultRepository
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.metadata_models import Metadata
from core.infrastructure.db.plugin_models import Plugin
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.metadata_repository import MetadataRepository
from core.infrastructure.plugin_repository import PluginRepository

REPO_ROOT = Path(__file__).resolve().parents[3]


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.cmd_opts = Namespace(x=[f"db_path={db_path}"])
    return cfg


class _Env:
    def __init__(
        self,
        engine: AsyncEngine,
        photo_repo: PhotoRepository,
        library_root_repo: LibraryRootRepository,
        metadata_repo: MetadataRepository,
        ai_results: AiResultRepository,
        plugin_repo: PluginRepository,
    ) -> None:
        self.engine = engine
        self.photo_repo = photo_repo
        self.library_root_repo = library_root_repo
        self.metadata_repo = metadata_repo
        self.ai_results = ai_results
        self.plugin_repo = plugin_repo


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    db_path = tmp_path / "fts.db"
    # env.py's migration runner does its own asyncio.run(); a plain call here
    # would fail since this fixture already runs inside pytest-asyncio's loop.
    await asyncio.to_thread(command.upgrade, _alembic_config(db_path), "head")

    engine = create_engine(db_path)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    try:
        yield _Env(
            engine,
            PhotoRepository(sessions, writer),
            LibraryRootRepository(sessions, writer),
            MetadataRepository(sessions, writer),
            AiResultRepository(sessions, writer),
            PluginRepository(sessions, writer),
        )
    finally:
        await writer.close()
        await engine.dispose()


async def _fts_query(env: _Env, table: str, match: str) -> list[tuple]:
    async with env.engine.connect() as conn:
        result = await conn.execute(
            text(f"SELECT * FROM {table} WHERE {table} MATCH :m"), {"m": match}
        )
        return list(result.fetchall())


async def _make_photo(env: _Env, relative_path: str = "beach-sunset.jpg") -> Photo:
    root = await env.library_root_repo.create(LibraryRoot(path="/library"))
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    return await env.photo_repo.create(
        Photo(
            library_root_id=root.id,
            relative_path=relative_path,
            relative_path_folded=relative_path.lower(),
            size_bytes=1,
            file_mtime=now,
            status="active",
        )
    )


async def test_photo_insert_is_searchable_by_filename(env: _Env) -> None:
    await _make_photo(env, "beach-sunset.jpg")

    rows = await _fts_query(env, "photo_fts", "beach")

    assert len(rows) == 1


async def test_photo_rename_updates_the_fts_shadow(env: _Env) -> None:
    photo = await _make_photo(env, "beach-sunset.jpg")
    photo.relative_path = "mountain-sunrise.jpg"
    await env.photo_repo.update(photo)

    assert await _fts_query(env, "photo_fts", "beach") == []
    assert len(await _fts_query(env, "photo_fts", "mountain")) == 1


async def test_metadata_insert_is_searchable_by_camera_make(env: _Env) -> None:
    photo = await _make_photo(env)

    await env.metadata_repo.upsert(
        Metadata(photo_id=photo.id, camera_make="Canon", camera_model="EOS R5", raw_exif_blob={})
    )

    rows = await _fts_query(env, "metadata_fts", "Canon")
    assert len(rows) == 1


async def test_metadata_update_replaces_the_fts_shadow(env: _Env) -> None:
    photo = await _make_photo(env)
    await env.metadata_repo.upsert(
        Metadata(photo_id=photo.id, camera_make="Canon", raw_exif_blob={})
    )

    await env.metadata_repo.upsert(
        Metadata(photo_id=photo.id, camera_make="Nikon", raw_exif_blob={})
    )

    assert await _fts_query(env, "metadata_fts", "Canon") == []
    assert len(await _fts_query(env, "metadata_fts", "Nikon")) == 1


async def test_current_ai_result_is_searchable(env: _Env) -> None:
    photo = await _make_photo(env)
    await env.plugin_repo.upsert(
        Plugin(
            id="blip2-caption",
            name="Captioner",
            capability_types="caption",
            version="1.0.0",
            source="builtin",
            enabled=True,
        )
    )

    await env.ai_results.record_result(
        photo_id=photo.id,
        plugin_id="blip2-caption",
        capability="caption",
        model_version="blip2-base@1",
        payload={"caption": "a dog running on the beach"},
        confidence=0.9,
    )

    rows = await _fts_query(env, "ai_result_fts", "beach")
    assert len(rows) == 1


async def test_superseded_ai_result_drops_out_of_search_immediately(env: _Env) -> None:
    photo = await _make_photo(env)
    await env.plugin_repo.upsert(
        Plugin(
            id="blip2-caption",
            name="Captioner",
            capability_types="caption",
            version="1.0.0",
            source="builtin",
            enabled=True,
        )
    )
    await env.ai_results.record_result(
        photo_id=photo.id,
        plugin_id="blip2-caption",
        capability="caption",
        model_version="blip2-base@1",
        payload={"caption": "a dog running on the beach"},
        confidence=0.9,
    )

    await env.ai_results.record_result(
        photo_id=photo.id,
        plugin_id="blip2-caption",
        capability="caption",
        model_version="blip2-base@2",
        payload={"caption": "a cat sleeping on the sofa"},
        confidence=0.95,
    )

    assert await _fts_query(env, "ai_result_fts", "beach") == []
    assert len(await _fts_query(env, "ai_result_fts", "sofa")) == 1
