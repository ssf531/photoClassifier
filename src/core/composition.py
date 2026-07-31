import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alembic.config import Config
from fastapi import FastAPI

from alembic import command
from core.api.app import create_app
from core.domain.scheduler import TaskScheduler
from core.domain.settings import AppSettings, data_dir, models_dir, thumbnails_dir
from core.infrastructure.ai_result_repository import AiResultRepository, EmbeddingRefRepository
from core.infrastructure.clip_embedding_provider import ClipEmbeddingProvider
from core.infrastructure.collection_manager import CollectionManager
from core.infrastructure.collection_repository import (
    CollectionItemRepository,
    CollectionRepository,
    SmartCollectionRuleRepository,
)
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.duplicate_repository import DuplicateGroupMemberRepository
from core.infrastructure.embedding_service import DefaultEmbeddingService
from core.infrastructure.fts_search_index import FtsTextSearchIndex
from core.infrastructure.gpu_resource_manager import (
    create_inference_semaphore,
    select_execution_provider,
)
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.metadata_repository import MetadataRepository
from core.infrastructure.plugin_discovery import discover_plugins
from core.infrastructure.plugin_lifecycle import sync_discovered_plugins
from core.infrastructure.plugin_repository import PluginRepository
from core.infrastructure.recommendation_engine import RecommendationEngine
from core.infrastructure.scan_job import SCAN_JOB_TYPE, create_scan_job_handler
from core.infrastructure.scheduler import InProcessTaskScheduler, JobItemRepository, JobRepository
from core.infrastructure.search_service import DefaultSearchService
from core.infrastructure.settings_toml import TomlSettingsService
from core.infrastructure.thumbnail_cache import ThumbnailCacheManager
from core.infrastructure.thumbnail_service import ThumbnailService
from core.infrastructure.vec_embedding_index import SqliteVecEmbeddingIndex
from core.logging_setup import configure_logging

_CLIP_PROVIDER_ID = "clip"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUILTIN_PLUGINS_DIR = Path(__file__).resolve().parent / "plugins"
_BYTES_PER_MB = 1024 * 1024


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

    scheduler = InProcessTaskScheduler(
        JobRepository(sessions, writer), JobItemRepository(sessions, writer)
    )
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

    await sync_discovered_plugins(discover_plugins(_BUILTIN_PLUGINS_DIR), plugin_repo)

    scheduler.register_handler(
        SCAN_JOB_TYPE,
        create_scan_job_handler(
            photo_repo,
            library_root_repo,
            grace_period_days=settings.missing_photo_grace_period_days,
        ),
    )

    execution_provider = select_execution_provider(override=settings.gpu_execution_provider)
    clip_provider = ClipEmbeddingProvider(
        models_dir(), create_inference_semaphore(), execution_provider
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
    recommendation_engine = RecommendationEngine(
        ai_result_repo, DuplicateGroupMemberRepository(sessions, writer)
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
    )

    return Composition(settings=settings, scheduler=scheduler, app=app)
