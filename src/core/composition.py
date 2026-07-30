from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from core.api.app import create_app
from core.domain.scheduler import TaskScheduler
from core.domain.settings import AppSettings, data_dir, models_dir
from core.infrastructure.ai_result_repository import AiResultRepository, EmbeddingRefRepository
from core.infrastructure.clip_embedding_provider import ClipEmbeddingProvider
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.embedding_service import DefaultEmbeddingService
from core.infrastructure.fts_search_index import FtsTextSearchIndex
from core.infrastructure.gpu_resource_manager import (
    create_inference_semaphore,
    select_execution_provider,
)
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.metadata_repository import MetadataRepository
from core.infrastructure.plugin_repository import PluginRepository
from core.infrastructure.scheduler import InProcessTaskScheduler, JobItemRepository, JobRepository
from core.infrastructure.search_service import DefaultSearchService
from core.infrastructure.settings_toml import TomlSettingsService
from core.infrastructure.vec_embedding_index import SqliteVecEmbeddingIndex
from core.logging_setup import configure_logging

_CLIP_PROVIDER_ID = "clip"


@dataclass
class Composition:
    settings: AppSettings
    scheduler: TaskScheduler
    app: FastAPI


def compose(**settings_overrides: Any) -> Composition:
    settings_service = TomlSettingsService(**settings_overrides)
    settings = settings_service.get()

    configure_logging(json_output=False, level=settings.log_level)

    data_dir().mkdir(parents=True, exist_ok=True)
    engine = create_engine(data_dir() / "photo-intelligence.db")
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    scheduler: TaskScheduler = InProcessTaskScheduler(
        JobRepository(sessions, writer), JobItemRepository(sessions, writer)
    )
    library_root_repo = LibraryRootRepository(sessions, writer)
    photo_repo = PhotoRepository(sessions, writer)
    metadata_repo = MetadataRepository(sessions, writer)
    ai_result_repo = AiResultRepository(sessions, writer)
    embedding_refs = EmbeddingRefRepository(sessions, writer)
    plugin_repo = PluginRepository(sessions, writer)

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

    app = create_app(
        scheduler=scheduler,
        settings=settings,
        photo_repo=photo_repo,
        metadata_repo=metadata_repo,
        ai_result_repo=ai_result_repo,
        search_service=search_service,
        settings_service=settings_service,
        plugin_repo=plugin_repo,
    )

    return Composition(settings=settings, scheduler=scheduler, app=app)
