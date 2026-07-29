import asyncio
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy.engine import Connection

from alembic import context
from core.domain.settings import data_dir
from core.infrastructure.db import (
    job_models,  # noqa: F401 -- registers models on Base.metadata
    library_models,  # noqa: F401 -- registers models on Base.metadata
    metadata_models,  # noqa: F401 -- registers models on Base.metadata
)
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_db_path() -> Path:
    override = context.get_x_argument(as_dictionary=True).get("db_path")
    if override:
        return Path(override)
    return data_dir() / "photo-intelligence.db"


def run_migrations_offline() -> None:
    url = f"sqlite+aiosqlite:///{_resolve_db_path()}"
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_engine(_resolve_db_path())

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
