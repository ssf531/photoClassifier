import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.domain.plugins import Capability
from core.domain.providers import ImageRef
from core.infrastructure.ai_result_repository import AiResultRepository
from core.infrastructure.analysis_pipeline import (
    CAPABILITY_UNAVAILABLE,
    PROVIDER_ERROR,
    AnalysisPipeline,
)
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.plugin_models import Plugin
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.plugin_repository import PluginRepository
from core.infrastructure.provider_registry import ProviderRegistry
from core.infrastructure.quality_provider import (
    MODEL_VERSION as QUALITY_MODEL_VERSION,
)
from core.infrastructure.quality_provider import (
    PROVIDER_ID as QUALITY_PROVIDER_ID,
)
from core.infrastructure.quality_provider import QualityAssessmentProvider

QUALITY_FIXTURES = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "quality"


@dataclass(frozen=True)
class _FakeResult:
    provider_id: str
    model_version: str
    confidence: float
    raw_payload: dict[str, object]


class _RaisingProvider:
    async def tag(self, image: ImageRef) -> _FakeResult:
        raise RuntimeError("provider blew up")


async def _quality_invoker(provider: QualityAssessmentProvider, image: ImageRef) -> _FakeResult:
    result = await provider.assess(image)
    return _FakeResult(
        result.provider_id, result.model_version, result.confidence, result.raw_payload
    )


async def _raising_invoker(provider: _RaisingProvider, image: ImageRef) -> _FakeResult:
    return await provider.tag(image)


@pytest.fixture
async def env(
    tmp_path: Path,
) -> AsyncIterator[tuple[AiResultRepository, PhotoRepository, uuid.UUID, uuid.UUID]]:
    engine = create_engine(tmp_path / "pipeline.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    photo_repo = PhotoRepository(sessions, writer)
    library_root_repo = LibraryRootRepository(sessions, writer)
    plugin_repo = PluginRepository(sessions, writer)
    ai_results = AiResultRepository(sessions, writer)

    root = await library_root_repo.create(LibraryRoot(path=str(QUALITY_FIXTURES)))
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    photo = await photo_repo.create(
        Photo(
            library_root_id=root.id,
            relative_path="normal.png",
            relative_path_folded="normal.png",
            size_bytes=1,
            file_mtime=now,
            status="active",
        )
    )
    await plugin_repo.upsert(
        Plugin(
            id=QUALITY_PROVIDER_ID,
            name="Quality",
            capability_types="quality",
            version="1.0.0",
            source="builtin",
            enabled=True,
        )
    )

    try:
        yield ai_results, photo_repo, photo.id, root.id
    finally:
        await writer.close()
        await engine.dispose()


async def test_successful_call_persists_ai_result(
    env: tuple[AiResultRepository, PhotoRepository, uuid.UUID, uuid.UUID],
) -> None:
    ai_results, _, photo_id, _ = env
    registry = ProviderRegistry({Capability.QUALITY: QualityAssessmentProvider()})
    pipeline = AnalysisPipeline(registry, ai_results, {Capability.QUALITY: _quality_invoker})
    image = ImageRef(photo_id=photo_id, path=QUALITY_FIXTURES / "normal.png")

    report = await pipeline.run_batch([image], [Capability.QUALITY])

    assert report.succeeded == 1
    assert report.failures == []
    current = await ai_results.list_current_by_photo(photo_id)
    assert len(current) == 1
    assert current[0].capability == "quality"
    assert current[0].model_version == QUALITY_MODEL_VERSION
    assert current[0].plugin_id == QUALITY_PROVIDER_ID


async def test_missing_provider_is_recorded_as_capability_unavailable(
    env: tuple[AiResultRepository, PhotoRepository, uuid.UUID, uuid.UUID],
) -> None:
    ai_results, _, photo_id, _ = env
    registry = ProviderRegistry({})
    pipeline = AnalysisPipeline(registry, ai_results, {Capability.QUALITY: _quality_invoker})
    image = ImageRef(photo_id=photo_id, path=QUALITY_FIXTURES / "normal.png")

    report = await pipeline.run_batch([image], [Capability.QUALITY])

    assert report.succeeded == 0
    assert len(report.failures) == 1
    assert report.failures[0].error_code == CAPABILITY_UNAVAILABLE
    assert await ai_results.list_current_by_photo(photo_id) == []


async def test_provider_exception_is_recorded_and_does_not_abort_the_batch(
    env: tuple[AiResultRepository, PhotoRepository, uuid.UUID, uuid.UUID],
) -> None:
    ai_results, photo_repo, photo_id, library_root_id = env
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    other_photo = await photo_repo.create(
        Photo(
            library_root_id=library_root_id,
            relative_path="sharp.png",
            relative_path_folded="sharp.png",
            size_bytes=1,
            file_mtime=now,
            status="active",
        )
    )
    registry = ProviderRegistry(
        {Capability.TAG: _RaisingProvider(), Capability.QUALITY: QualityAssessmentProvider()}
    )
    pipeline = AnalysisPipeline(
        registry,
        ai_results,
        {Capability.TAG: _raising_invoker, Capability.QUALITY: _quality_invoker},
    )
    images = [
        ImageRef(photo_id=photo_id, path=QUALITY_FIXTURES / "normal.png"),
        ImageRef(photo_id=other_photo.id, path=QUALITY_FIXTURES / "sharp.png"),
    ]

    report = await pipeline.run_batch(images, [Capability.TAG, Capability.QUALITY])

    assert report.succeeded == 2  # QUALITY succeeded for both photos
    assert len(report.failures) == 2  # TAG failed for both photos
    assert all(f.error_code == PROVIDER_ERROR for f in report.failures)
    assert len(await ai_results.list_current_by_photo(photo_id)) == 1
    assert len(await ai_results.list_current_by_photo(other_photo.id)) == 1


async def test_subset_of_capabilities_produces_results_for_exactly_that_subset(
    env: tuple[AiResultRepository, PhotoRepository, uuid.UUID, uuid.UUID],
) -> None:
    ai_results, _, photo_id, _ = env
    registry = ProviderRegistry(
        {Capability.TAG: _RaisingProvider(), Capability.QUALITY: QualityAssessmentProvider()}
    )
    pipeline = AnalysisPipeline(
        registry,
        ai_results,
        {Capability.TAG: _raising_invoker, Capability.QUALITY: _quality_invoker},
    )
    image = ImageRef(photo_id=photo_id, path=QUALITY_FIXTURES / "normal.png")

    report = await pipeline.run_batch([image], [Capability.QUALITY])

    assert report.succeeded == 1
    assert report.failures == []
    current = await ai_results.list_current_by_photo(photo_id)
    assert {row.capability for row in current} == {"quality"}
