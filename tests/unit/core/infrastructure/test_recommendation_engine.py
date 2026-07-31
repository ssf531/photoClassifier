import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.domain.plugins import Capability
from core.domain.recommendations import RecommendationCategory
from core.infrastructure.ai_result_repository import AiResultRepository
from core.infrastructure.db.base import Base
from core.infrastructure.db.duplicate_models import DuplicateGroup, DuplicateGroupMember
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.plugin_models import Plugin
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.duplicate_repository import (
    DuplicateGroupMemberRepository,
    DuplicateGroupRepository,
)
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.plugin_repository import PluginRepository
from core.infrastructure.recommendation_engine import RecommendationEngine


class _Env:
    def __init__(
        self,
        engine: RecommendationEngine,
        photo_repo: PhotoRepository,
        ai_results: AiResultRepository,
        duplicate_groups: DuplicateGroupRepository,
        duplicate_members: DuplicateGroupMemberRepository,
        library_root_id: uuid.UUID,
    ) -> None:
        self.engine = engine
        self.photo_repo = photo_repo
        self.ai_results = ai_results
        self.duplicate_groups = duplicate_groups
        self.duplicate_members = duplicate_members
        self.library_root_id = library_root_id

    async def make_photo(self) -> uuid.UUID:
        now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
        name = f"{uuid.uuid4()}.jpg"
        photo = await self.photo_repo.create(
            Photo(
                library_root_id=self.library_root_id,
                relative_path=name,
                relative_path_folded=name.lower(),
                size_bytes=1,
                file_mtime=now,
                status="active",
            )
        )
        return photo.id


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "recommendations.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    library_root_repo = LibraryRootRepository(sessions, writer)
    root = await library_root_repo.create(LibraryRoot(path="/library"))
    photo_repo = PhotoRepository(sessions, writer)
    ai_results = AiResultRepository(sessions, writer)
    duplicate_groups = DuplicateGroupRepository(sessions, writer)
    duplicate_members = DuplicateGroupMemberRepository(sessions, writer)

    plugin_repo = PluginRepository(sessions, writer)
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

    recommendation_engine = RecommendationEngine(ai_results, duplicate_members)

    try:
        yield _Env(
            recommendation_engine,
            photo_repo,
            ai_results,
            duplicate_groups,
            duplicate_members,
            root.id,
        )
    finally:
        await writer.close()
        await engine.dispose()


async def _by_category(
    engine: RecommendationEngine,
) -> dict[RecommendationCategory, set[uuid.UUID]]:
    recommendations = await engine.list_recommendations()
    return {r.category: set(r.photo_ids) for r in recommendations}


async def test_screenshots_category_identifies_only_photos_tagged_screenshot(env: _Env) -> None:
    screenshot_photo = await env.make_photo()
    dog_photo = await env.make_photo()
    await env.ai_results.record_result(
        photo_id=screenshot_photo,
        plugin_id="clip-zero-shot-tagging",
        capability=Capability.TAG.value,
        model_version="v1",
        payload={"tags": [{"label": "screenshot", "confidence": 0.9}]},
        confidence=0.9,
    )
    await env.ai_results.record_result(
        photo_id=dog_photo,
        plugin_id="clip-zero-shot-tagging",
        capability=Capability.TAG.value,
        model_version="v1",
        payload={"tags": [{"label": "dog", "confidence": 0.8}]},
        confidence=0.8,
    )

    by_category = await _by_category(env.engine)

    assert by_category[RecommendationCategory.SCREENSHOTS] == {screenshot_photo}


async def test_low_quality_category_identifies_blurry_and_exposure_flagged_photos(
    env: _Env,
) -> None:
    blurry_photo = await env.make_photo()
    overexposed_photo = await env.make_photo()
    good_photo = await env.make_photo()
    await env.ai_results.record_result(
        photo_id=blurry_photo,
        plugin_id="builtin-quality",
        capability=Capability.QUALITY.value,
        model_version="v1",
        payload={
            "sharpness_variance": 5.0,
            "mean_brightness": 120.0,
            "is_blurry": True,
            "is_underexposed": False,
            "is_overexposed": False,
        },
        confidence=1.0,
    )
    await env.ai_results.record_result(
        photo_id=overexposed_photo,
        plugin_id="builtin-quality",
        capability=Capability.QUALITY.value,
        model_version="v1",
        payload={
            "sharpness_variance": 200.0,
            "mean_brightness": 240.0,
            "is_blurry": False,
            "is_underexposed": False,
            "is_overexposed": True,
        },
        confidence=1.0,
    )
    await env.ai_results.record_result(
        photo_id=good_photo,
        plugin_id="builtin-quality",
        capability=Capability.QUALITY.value,
        model_version="v1",
        payload={
            "sharpness_variance": 200.0,
            "mean_brightness": 120.0,
            "is_blurry": False,
            "is_underexposed": False,
            "is_overexposed": False,
        },
        confidence=1.0,
    )

    by_category = await _by_category(env.engine)

    assert by_category[RecommendationCategory.LOW_QUALITY] == {blurry_photo, overexposed_photo}


async def test_near_duplicates_category_identifies_all_members_of_duplicate_groups(
    env: _Env,
) -> None:
    keeper = await env.make_photo()
    duplicate = await env.make_photo()
    unrelated = await env.make_photo()
    group = await env.duplicate_groups.create(DuplicateGroup(detection_method="dhash@1"))
    await env.duplicate_members.create(
        DuplicateGroupMember(
            group_id=group.id, photo_id=keeper, similarity_score=1.0, is_recommended_keeper=True
        )
    )
    await env.duplicate_members.create(
        DuplicateGroupMember(
            group_id=group.id,
            photo_id=duplicate,
            similarity_score=0.95,
            is_recommended_keeper=False,
        )
    )
    assert unrelated  # keep the unrelated photo alive without asserting it belongs anywhere

    by_category = await _by_category(env.engine)

    assert by_category[RecommendationCategory.NEAR_DUPLICATES] == {keeper, duplicate}


async def test_a_photo_with_no_matching_signal_appears_in_no_category(env: _Env) -> None:
    plain_photo = await env.make_photo()

    by_category = await _by_category(env.engine)

    assert all(plain_photo not in members for members in by_category.values())
