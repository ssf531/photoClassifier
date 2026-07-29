import asyncio
import uuid
from argparse import Namespace
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from core.infrastructure.ai_result_repository import AiResultRepository
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.plugin_models import Plugin
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.fts_search_index import FtsTextSearchIndex
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
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
        index: FtsTextSearchIndex,
        photo_repo: PhotoRepository,
        ai_results: AiResultRepository,
        plugin_repo: PluginRepository,
        library_root_id: uuid.UUID,
    ) -> None:
        self.index = index
        self.photo_repo = photo_repo
        self.ai_results = ai_results
        self.plugin_repo = plugin_repo
        self.library_root_id = library_root_id


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    db_path = tmp_path / "fts_search.db"
    await asyncio.to_thread(command.upgrade, _alembic_config(db_path), "head")

    engine = create_engine(db_path)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)
    library_root_repo = LibraryRootRepository(sessions, writer)
    root = await library_root_repo.create(LibraryRoot(path="/library"))

    try:
        yield _Env(
            FtsTextSearchIndex(sessions),
            PhotoRepository(sessions, writer),
            AiResultRepository(sessions, writer),
            PluginRepository(sessions, writer),
            root.id,
        )
    finally:
        await writer.close()
        await engine.dispose()


async def _make_photo(env: _Env, relative_path: str) -> Photo:
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    return await env.photo_repo.create(
        Photo(
            library_root_id=env.library_root_id,
            relative_path=relative_path,
            relative_path_folded=relative_path.lower(),
            size_bytes=1,
            file_mtime=now,
            status="active",
        )
    )


async def test_search_finds_a_photo_by_filename(env: _Env) -> None:
    photo = await _make_photo(env, "grand-canyon-hike.jpg")

    hits = await env.index.search("canyon", limit=10)

    assert [hit.photo_id for hit in hits] == [photo.id]


async def test_search_returns_no_hits_for_an_unmatched_query(env: _Env) -> None:
    await _make_photo(env, "grand-canyon-hike.jpg")

    hits = await env.index.search("nonexistent-term-xyz", limit=10)

    assert hits == []


async def test_a_photo_matching_two_shadow_tables_ranks_above_one_matching_only_one(
    env: _Env,
) -> None:
    double_match = await _make_photo(env, "beach-sunset.jpg")
    single_match = await _make_photo(env, "beach-noon.jpg")
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
        photo_id=double_match.id,
        plugin_id="blip2-caption",
        capability="caption",
        model_version="blip2-base@1",
        payload={"caption": "a beach at sunset"},
        confidence=0.9,
    )

    hits = await env.index.search("beach", limit=10)

    assert [hit.photo_id for hit in hits] == [double_match.id, single_match.id]
    assert hits[0].score > hits[1].score


async def test_limit_and_offset_paginate_the_ranked_results(env: _Env) -> None:
    photos = [await _make_photo(env, f"mountain-trip-{i}.jpg") for i in range(5)]

    first_page = await env.index.search("mountain", limit=2, offset=0)
    second_page = await env.index.search("mountain", limit=2, offset=2)

    assert len(first_page) == 2
    assert len(second_page) == 2
    seen_ids = {hit.photo_id for hit in first_page} | {hit.photo_id for hit in second_page}
    assert seen_ids <= {p.id for p in photos}
    assert {hit.photo_id for hit in first_page}.isdisjoint({hit.photo_id for hit in second_page})
