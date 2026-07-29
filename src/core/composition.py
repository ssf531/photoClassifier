from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from core.api.app import create_app
from core.domain.scheduler import TaskScheduler
from core.domain.settings import AppSettings, data_dir
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.scheduler import InProcessTaskScheduler, JobItemRepository, JobRepository
from core.infrastructure.settings_toml import TomlSettingsService
from core.logging_setup import configure_logging


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

    app = create_app(scheduler=scheduler, settings=settings)

    return Composition(settings=settings, scheduler=scheduler, app=app)
