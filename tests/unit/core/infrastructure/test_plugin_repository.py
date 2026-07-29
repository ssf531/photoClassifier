from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.plugin_models import Plugin
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.plugin_repository import PluginRepository


@pytest.fixture
async def repo(tmp_path: Path) -> AsyncIterator[PluginRepository]:
    engine = create_engine(tmp_path / "plugin.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)
    try:
        yield PluginRepository(sessions, writer)
    finally:
        await writer.close()
        await engine.dispose()


def _plugin(plugin_id: str = "onnx-clip-embedding", enabled: bool = False) -> Plugin:
    return Plugin(
        id=plugin_id,
        name="CLIP Embedding",
        capability_types="embedding",
        version="1.0.0",
        source="builtin",
        enabled=enabled,
    )


async def test_get_returns_none_for_unknown_id(repo: PluginRepository) -> None:
    assert await repo.get("does-not-exist") is None


async def test_upsert_inserts_new_plugin(repo: PluginRepository) -> None:
    await repo.upsert(_plugin())

    fetched = await repo.get("onnx-clip-embedding")
    assert fetched is not None
    assert fetched.name == "CLIP Embedding"
    assert fetched.enabled is False


async def test_upsert_updates_existing_plugin(repo: PluginRepository) -> None:
    await repo.upsert(_plugin())
    await repo.upsert(_plugin(enabled=True))

    fetched = await repo.get("onnx-clip-embedding")
    assert fetched is not None
    assert fetched.enabled is True


async def test_list_orders_by_id(repo: PluginRepository) -> None:
    await repo.upsert(_plugin("b-plugin"))
    await repo.upsert(_plugin("a-plugin"))

    plugins = await repo.list(limit=10, offset=0)

    assert [p.id for p in plugins] == ["a-plugin", "b-plugin"]


async def test_list_enabled_only_returns_enabled_plugins(repo: PluginRepository) -> None:
    await repo.upsert(_plugin("disabled-plugin", enabled=False))
    await repo.upsert(_plugin("enabled-plugin", enabled=True))

    plugins = await repo.list_enabled()

    assert [p.id for p in plugins] == ["enabled-plugin"]
