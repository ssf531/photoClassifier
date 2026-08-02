import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alembic.config import Config
from fastapi import FastAPI

from alembic import command
from core.api.app import create_app
from core.domain.plugins import Capability
from core.domain.providers import CaptionResult, ImageRef, QualityResult, TagResult
from core.domain.scheduler import TaskScheduler
from core.domain.settings import AppSettings, bundle_root, data_dir, models_dir, thumbnails_dir
from core.infrastructure.ai_result_repository import AiResultRepository, EmbeddingRefRepository
from core.infrastructure.analysis_job import ANALYSIS_JOB_TYPE, create_analysis_job_handler
from core.infrastructure.analysis_pipeline import AnalysisPipeline
from core.infrastructure.caption_provider import CaptioningProvider
from core.infrastructure.clip_embedding_provider import ClipEmbeddingProvider
from core.infrastructure.collection_manager import CollectionManager
from core.infrastructure.collection_repository import (
    CollectionItemRepository,
    CollectionRepository,
    SmartCollectionRuleRepository,
    UserDataRepository,
)
from core.infrastructure.copy_export_manager import CopyExportManager
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.diagnostics_bundle import DiagnosticsBundleBuilder
from core.infrastructure.duplicate_repository import (
    DuplicateGroupMemberRepository,
    DuplicateGroupRepository,
)
from core.infrastructure.duplicate_review_service import DuplicateReviewService
from core.infrastructure.embedding_service import DefaultEmbeddingService
from core.infrastructure.exiftool_process import ExifToolProcess, find_exiftool
from core.infrastructure.export_repository import XmpExportRecordRepository
from core.infrastructure.fts_search_index import FtsTextSearchIndex
from core.infrastructure.gpu_resource_manager import (
    create_inference_semaphore,
    select_execution_provider,
)
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.metadata_repository import MetadataRepository
from core.infrastructure.plugin_discovery import discover_plugins
from core.infrastructure.plugin_lifecycle import list_enabled_manifests, sync_discovered_plugins
from core.infrastructure.plugin_repository import PluginRepository
from core.infrastructure.problems_service import ProblemsService
from core.infrastructure.provider_registry import ProviderRegistry
from core.infrastructure.quality_provider import QualityAssessmentProvider
from core.infrastructure.recommendation_engine import RecommendationEngine
from core.infrastructure.scan_job import SCAN_JOB_TYPE, create_scan_job_handler
from core.infrastructure.scheduler import InProcessTaskScheduler, JobItemRepository, JobRepository
from core.infrastructure.search_service import DefaultSearchService
from core.infrastructure.settings_toml import TomlSettingsService
from core.infrastructure.tag_provider import TaggingProvider
from core.infrastructure.thumbnail_cache import ThumbnailCacheManager
from core.infrastructure.thumbnail_service import ThumbnailService
from core.infrastructure.vec_embedding_index import SqliteVecEmbeddingIndex
from core.infrastructure.xmp_export_manager import XmpExportManager
from core.logging_setup import configure_logging

_CLIP_PROVIDER_ID = "clip"
_REPO_ROOT = bundle_root()
_BUILTIN_PLUGINS_DIR = bundle_root() / "src" / "core" / "plugins"
_BYTES_PER_MB = 1024 * 1024


async def _invoke_caption(provider: CaptioningProvider, image: ImageRef) -> CaptionResult:
    return await provider.caption(image)


async def _invoke_tag(provider: TaggingProvider, image: ImageRef) -> TagResult:
    return await provider.tag(image)


async def _invoke_quality(provider: QualityAssessmentProvider, image: ImageRef) -> QualityResult:
    return await provider.assess(image)


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "alembic"))
    cfg.cmd_opts = argparse.Namespace(x=[f"db_path={db_path}"])
    return cfg


async def _migrate_to_head(db_path: Path) -> None:
    # alembic's `command.upgrade` calls `asyncio.run()` internally, so it
    # can't be awaited directly from within compose()'s already-running loop.
    await asyncio.to_thread(command.upgrade, _alembic_config(db_path), "head")


@dataclass
class Composition:
    settings: AppSettings
    scheduler: TaskScheduler
    app: FastAPI


async def compose(**settings_overrides: Any) -> Composition:
    settings_service = TomlSettingsService(**settings_overrides)
    settings = settings_service.get()

    configure_logging(json_output=False, level=settings.log_level)

    data_dir().mkdir(parents=True, exist_ok=True)
    db_path = data_dir() / "photo-intelligence.db"
    await _migrate_to_head(db_path)

    engine = create_engine(db_path)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    job_item_repo = JobItemRepository(sessions, writer)
    scheduler = InProcessTaskScheduler(JobRepository(sessions, writer), job_item_repo)
    library_root_repo = LibraryRootRepository(sessions, writer)
    photo_repo = PhotoRepository(sessions, writer)
    metadata_repo = MetadataRepository(sessions, writer)
    ai_result_repo = AiResultRepository(sessions, writer)
    embedding_refs = EmbeddingRefRepository(sessions, writer)
    plugin_repo = PluginRepository(sessions, writer)

    thumbnail_cache = ThumbnailCacheManager(
        thumbnails_dir(), settings.thumbnail_cache_max_mb * _BYTES_PER_MB
    )
    thumbnail_service = ThumbnailService(
        thumbnail_cache,
        photo_repo,
        library_root_repo,
        metadata_repo,
        grid_size_px=settings.thumbnail_grid_size_px,
        preview_size_px=settings.thumbnail_preview_size_px,
    )

    discovery = discover_plugins(_BUILTIN_PLUGINS_DIR)
    await sync_discovered_plugins(discovery, plugin_repo)
    enabled_capabilities = {
        manifest.capability for manifest in await list_enabled_manifests(discovery, plugin_repo)
    }

    execution_provider = select_execution_provider(override=settings.gpu_execution_provider)
    # One shared semaphore across every ONNX-inference provider (ADR-0009):
    # a single global Semaphore(1) serializes GPU/CPU inference regardless of
    # which capability is calling, so it must be constructed once here and
    # passed to each provider, never created per-provider.
    inference_semaphore = create_inference_semaphore()
    clip_provider = ClipEmbeddingProvider(models_dir(), inference_semaphore, execution_provider)
    caption_provider = CaptioningProvider(models_dir(), inference_semaphore, execution_provider)
    tagging_provider = TaggingProvider(clip_provider)
    quality_provider = QualityAssessmentProvider()

    # A capability is only registered with the pipeline if its plugin is
    # enabled AND (where applicable) its model is actually downloaded --
    # otherwise `ProviderRegistry.get_provider` raises `UnresolvedCapabilityError`,
    # which the pipeline records as a clean `capability_unavailable` failure
    # (SDD §16.4 degraded mode) rather than a provider crashing on first use.
    capability_providers: dict[Capability, Any] = {}
    if Capability.CAPTION in enabled_capabilities and caption_provider.is_available():
        capability_providers[Capability.CAPTION] = caption_provider
    if Capability.TAG in enabled_capabilities and tagging_provider.is_available():
        capability_providers[Capability.TAG] = tagging_provider
    if Capability.QUALITY in enabled_capabilities:
        capability_providers[Capability.QUALITY] = quality_provider

    provider_registry = ProviderRegistry(capability_providers)
    analysis_pipeline = AnalysisPipeline(
        provider_registry,
        ai_result_repo,
        {
            Capability.CAPTION: _invoke_caption,
            Capability.TAG: _invoke_tag,
            Capability.QUALITY: _invoke_quality,
        },
    )

    scheduler.register_handler(
        ANALYSIS_JOB_TYPE,
        create_analysis_job_handler(
            analysis_pipeline, photo_repo, library_root_repo, job_item_repo
        ),
    )
    scheduler.register_handler(
        SCAN_JOB_TYPE,
        create_scan_job_handler(
            photo_repo,
            library_root_repo,
            grace_period_days=settings.missing_photo_grace_period_days,
            scheduler=scheduler,
            capabilities=list(provider_registry.capabilities()),
        ),
    )
    problems_service = ProblemsService(
        job_item_repo, scheduler, list(provider_registry.capabilities())
    )

    vec_index = SqliteVecEmbeddingIndex(sessions, writer)
    embedding_service = DefaultEmbeddingService(
        providers={_CLIP_PROVIDER_ID: clip_provider},
        index=vec_index,
        embedding_refs=embedding_refs,
        photo_repo=photo_repo,
        library_root_repo=library_root_repo,
        default_provider=_CLIP_PROVIDER_ID,
    )
    search_service = DefaultSearchService(
        text_index=FtsTextSearchIndex(sessions),
        embedding_index=vec_index,
        embedding_service=embedding_service,
        read_sessions=sessions,
        default_embedding_provider=_CLIP_PROVIDER_ID,
    )
    collection_manager = CollectionManager(
        CollectionRepository(sessions, writer),
        CollectionItemRepository(sessions, writer),
        SmartCollectionRuleRepository(sessions, writer),
        search_service,
    )
    duplicate_group_member_repo = DuplicateGroupMemberRepository(sessions, writer)
    recommendation_engine = RecommendationEngine(ai_result_repo, duplicate_group_member_repo)
    duplicate_review_service = DuplicateReviewService(
        DuplicateGroupRepository(sessions, writer), duplicate_group_member_repo
    )

    # ExifTool is an optional system dependency (SDD §16.4 degraded mode):
    # XMP export simply isn't offered when it's absent, same as HEIC/GPU.
    # The one process instance is shared with the diagnostics bundle
    # (SDD §16.5's pinned ExifTool version) rather than spawning a second.
    exiftool_path = find_exiftool()
    exiftool_process = ExifToolProcess(exiftool_path) if exiftool_path is not None else None
    xmp_export_manager = (
        XmpExportManager(
            exiftool_process,
            photo_repo,
            library_root_repo,
            ai_result_repo,
            UserDataRepository(sessions, writer),
            XmpExportRecordRepository(sessions, writer),
        )
        if exiftool_process is not None
        else None
    )
    copy_export_manager = CopyExportManager(photo_repo, library_root_repo)
    diagnostics_bundle_builder = DiagnosticsBundleBuilder(
        settings_service,
        photo_repo,
        library_root_repo,
        plugin_repo,
        discovery.manifests,
        models_dir(),
        exiftool_process,
    )

    app = create_app(
        scheduler=scheduler,
        settings=settings,
        thumbnail_service=thumbnail_service,
        photo_repo=photo_repo,
        metadata_repo=metadata_repo,
        ai_result_repo=ai_result_repo,
        search_service=search_service,
        settings_service=settings_service,
        plugin_repo=plugin_repo,
        library_root_repo=library_root_repo,
        collection_manager=collection_manager,
        recommendation_engine=recommendation_engine,
        duplicate_review_service=duplicate_review_service,
        xmp_export_manager=xmp_export_manager,
        copy_export_manager=copy_export_manager,
        problems_service=problems_service,
        diagnostics_bundle_builder=diagnostics_bundle_builder,
    )

    return Composition(settings=settings, scheduler=scheduler, app=app)
