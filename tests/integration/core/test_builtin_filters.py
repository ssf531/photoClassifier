import asyncio
import uuid
from argparse import Namespace
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from core.domain.plugins import Capability
from core.domain.providers import Vector
from core.domain.search import ScoredPhoto, search_query_from_request
from core.infrastructure.ai_result_repository import AiResultRepository
from core.infrastructure.builtin_filters import BUILTIN_FILTER_PRESETS
from core.infrastructure.db.duplicate_models import DuplicateGroup, DuplicateGroupMember
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.plugin_models import Plugin
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.duplicate_repository import (
    DuplicateGroupMemberRepository,
    DuplicateGroupRepository,
)
from core.infrastructure.fts_search_index import FtsTextSearchIndex
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.plugin_repository import PluginRepository
from core.infrastructure.recommendation_engine import RecommendationEngine
from core.infrastructure.search_service import DefaultSearchService
from core.infrastructure.vec_embedding_index import SqliteVecEmbeddingIndex

REPO_ROOT = Path(__file__).resolve().parents[3]


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.cmd_opts = Namespace(x=[f"db_path={db_path}"])
    return cfg


class _UnusedEmbeddingService:
    """These tests only exercise `text`/`metadata` search modes."""

    async def embed(self, photo_id: uuid.UUID, provider: str) -> None:
        raise NotImplementedError

    async def similar_to(self, photo_id: uuid.UUID, k: int) -> list[ScoredPhoto]:
        raise NotImplementedError

    async def embed_text(self, query: str, provider: str) -> Vector:
        raise NotImplementedError


class _Env:
    def __init__(
        self,
        search_service: DefaultSearchService,
        recommendation_engine: RecommendationEngine,
        screenshot_photo_id: uuid.UUID,
        blurry_photo_id: uuid.UUID,
        duplicate_photo_ids: set[uuid.UUID],
    ) -> None:
        self.search_service = search_service
        self.recommendation_engine = recommendation_engine
        self.screenshot_photo_id = screenshot_photo_id
        self.blurry_photo_id = blurry_photo_id
        self.duplicate_photo_ids = duplicate_photo_ids


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    db_path = tmp_path / "builtin_filters.db"
    await asyncio.to_thread(command.upgrade, _alembic_config(db_path), "head")

    engine = create_engine(db_path)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    library_root_repo = LibraryRootRepository(sessions, writer)
    photo_repo = PhotoRepository(sessions, writer)
    ai_results = AiResultRepository(sessions, writer)
    plugin_repo = PluginRepository(sessions, writer)
    duplicate_groups = DuplicateGroupRepository(sessions, writer)
    duplicate_members = DuplicateGroupMemberRepository(sessions, writer)

    root = await library_root_repo.create(LibraryRoot(path="/library"))
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration

    async def make_photo(name: str) -> uuid.UUID:
        photo = await photo_repo.create(
            Photo(
                library_root_id=root.id,
                relative_path=name,
                relative_path_folded=name.lower(),
                size_bytes=1,
                file_mtime=now,
                status="active",
            )
        )
        return photo.id

    for plugin_id in ("clip-zero-shot-tagging", "builtin-quality"):
        await plugin_repo.upsert(
            Plugin(
                id=plugin_id,
                name=plugin_id,
                capability_types="tag",
                version="1.0.0",
                source="builtin",
            )
        )

    screenshot_photo_id = await make_photo("screenshot.jpg")
    await make_photo("dog.jpg")
    await ai_results.record_result(
        photo_id=screenshot_photo_id,
        plugin_id="clip-zero-shot-tagging",
        capability=Capability.TAG.value,
        model_version="tag-vocab-v1",
        payload={"tags": [{"label": "screenshot", "confidence": 0.9}]},
        confidence=0.9,
    )

    blurry_photo_id = await make_photo("blurry.jpg")
    sharp_photo_id = await make_photo("sharp.jpg")
    # No underexposed/overexposed flags set on either photo, so the "blurry"
    # preset's is_blurry-only criterion and the recommendation engine's
    # broader low_quality category (blurry OR under/overexposed) agree
    # exactly here -- that's the "same underlying criteria" this test needs.
    await ai_results.record_result(
        photo_id=blurry_photo_id,
        plugin_id="builtin-quality",
        capability=Capability.QUALITY.value,
        model_version="laplacian-exposure@1",
        payload={
            "sharpness_variance": 4.0,
            "mean_brightness": 120.0,
            "is_blurry": True,
            "is_underexposed": False,
            "is_overexposed": False,
        },
        confidence=1.0,
    )
    await ai_results.record_result(
        photo_id=sharp_photo_id,
        plugin_id="builtin-quality",
        capability=Capability.QUALITY.value,
        model_version="laplacian-exposure@1",
        payload={
            "sharpness_variance": 200.0,
            "mean_brightness": 120.0,
            "is_blurry": False,
            "is_underexposed": False,
            "is_overexposed": False,
        },
        confidence=1.0,
    )

    dup_a = await make_photo("dup-a.jpg")
    dup_b = await make_photo("dup-b.jpg")
    group = await duplicate_groups.create(DuplicateGroup(detection_method="dhash@1"))
    await duplicate_members.create(
        DuplicateGroupMember(
            group_id=group.id, photo_id=dup_a, similarity_score=1.0, is_recommended_keeper=True
        )
    )
    await duplicate_members.create(
        DuplicateGroupMember(
            group_id=group.id, photo_id=dup_b, similarity_score=0.9, is_recommended_keeper=False
        )
    )

    search_service = DefaultSearchService(
        text_index=FtsTextSearchIndex(sessions),
        embedding_index=SqliteVecEmbeddingIndex(sessions, writer),
        embedding_service=_UnusedEmbeddingService(),
        read_sessions=sessions,
        default_embedding_provider="clip",
    )
    recommendation_engine = RecommendationEngine(ai_results, duplicate_members)

    try:
        yield _Env(
            search_service,
            recommendation_engine,
            screenshot_photo_id,
            blurry_photo_id,
            {dup_a, dup_b},
        )
    finally:
        await writer.close()
        await engine.dispose()


def _preset_search_query(key: str):
    preset = next(p for p in BUILTIN_FILTER_PRESETS if p.key == key)
    return search_query_from_request(preset.search_query)


async def test_screenshots_preset_matches_the_recommendation_engine_category(env: _Env) -> None:
    results = await env.search_service.search(_preset_search_query("screenshots"))
    preset_ids = {r.photo_id for r in results.results}

    recommendations = await env.recommendation_engine.list_recommendations()
    engine_ids = next(r.photo_ids for r in recommendations if r.category == "screenshots")

    assert preset_ids == set(engine_ids) == {env.screenshot_photo_id}


async def test_blurry_preset_matches_the_recommendation_engine_low_quality_category(
    env: _Env,
) -> None:
    results = await env.search_service.search(_preset_search_query("blurry"))
    preset_ids = {r.photo_id for r in results.results}

    recommendations = await env.recommendation_engine.list_recommendations()
    engine_ids = next(r.photo_ids for r in recommendations if r.category == "low_quality")

    assert preset_ids == set(engine_ids) == {env.blurry_photo_id}


async def test_duplicates_preset_matches_the_recommendation_engine_category(env: _Env) -> None:
    results = await env.search_service.search(_preset_search_query("duplicates"))
    preset_ids = {r.photo_id for r in results.results}

    recommendations = await env.recommendation_engine.list_recommendations()
    engine_ids = next(r.photo_ids for r in recommendations if r.category == "near_duplicates")

    assert preset_ids == set(engine_ids) == env.duplicate_photo_ids
