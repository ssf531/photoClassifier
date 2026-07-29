from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from core.domain.plugins import Capability, ModelSource, PluginCompatibility, PluginManifest
from core.infrastructure.db.base import Base
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.plugin_discovery import DiscoveryResult
from core.infrastructure.plugin_lifecycle import (
    UnknownPluginError,
    disable_plugin,
    enable_plugin,
    list_enabled_manifests,
    sync_discovered_plugins,
)
from core.infrastructure.plugin_repository import PluginRepository


def _manifest(plugin_id: str, version: str = "1.0.0") -> PluginManifest:
    return PluginManifest(
        id=plugin_id,
        name=f"{plugin_id} provider",
        version=version,
        capability=Capability.EMBEDDING,
        entry_point="inproc",
        runtime="python",
        model_source=ModelSource.BUNDLED,
        compatibility=PluginCompatibility(core_api_version=">=1.0,<2.0"),
    )


@pytest.fixture
async def repo(tmp_path: Path) -> AsyncIterator[PluginRepository]:
    engine = create_engine(tmp_path / "lifecycle.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)
    try:
        yield PluginRepository(sessions, writer)
    finally:
        await writer.close()
        await engine.dispose()


async def test_sync_persists_newly_discovered_plugin_as_disabled(repo: PluginRepository) -> None:
    discovery = DiscoveryResult(manifests=[_manifest("clip-embedding")], errors=[])

    synced = await sync_discovered_plugins(discovery, repo)

    assert len(synced) == 1
    assert synced[0].enabled is False
    assert synced[0].capability_types == "embedding"


async def test_sync_preserves_enabled_flag_across_rediscovery(repo: PluginRepository) -> None:
    discovery = DiscoveryResult(manifests=[_manifest("clip-embedding")], errors=[])
    await sync_discovered_plugins(discovery, repo)
    await enable_plugin("clip-embedding", repo)

    resynced = await sync_discovered_plugins(
        DiscoveryResult(manifests=[_manifest("clip-embedding", version="1.1.0")], errors=[]), repo
    )

    assert resynced[0].enabled is True
    assert resynced[0].version == "1.1.0"


async def test_enable_plugin_persists_enabled_state(repo: PluginRepository) -> None:
    await sync_discovered_plugins(
        DiscoveryResult(manifests=[_manifest("clip-embedding")], errors=[]), repo
    )

    plugin = await enable_plugin("clip-embedding", repo)

    assert plugin.enabled is True
    assert (await repo.get("clip-embedding")).enabled is True  # type: ignore[union-attr]


async def test_disable_plugin_persists_disabled_state(repo: PluginRepository) -> None:
    await sync_discovered_plugins(
        DiscoveryResult(manifests=[_manifest("clip-embedding")], errors=[]), repo
    )
    await enable_plugin("clip-embedding", repo)

    plugin = await disable_plugin("clip-embedding", repo)

    assert plugin.enabled is False


async def test_enable_plugin_raises_for_unknown_id(repo: PluginRepository) -> None:
    with pytest.raises(UnknownPluginError):
        await enable_plugin("does-not-exist", repo)


async def test_disable_plugin_raises_for_unknown_id(repo: PluginRepository) -> None:
    with pytest.raises(UnknownPluginError):
        await disable_plugin("does-not-exist", repo)


async def test_list_enabled_manifests_excludes_disabled_and_undiscovered(
    repo: PluginRepository,
) -> None:
    discovery = DiscoveryResult(
        manifests=[_manifest("clip-embedding"), _manifest("blip2-caption")], errors=[]
    )
    await sync_discovered_plugins(discovery, repo)
    await enable_plugin("clip-embedding", repo)

    enabled = await list_enabled_manifests(discovery, repo)

    assert [manifest.id for manifest in enabled] == ["clip-embedding"]


async def test_list_enabled_manifests_excludes_plugin_no_longer_discovered(
    repo: PluginRepository,
) -> None:
    await sync_discovered_plugins(
        DiscoveryResult(manifests=[_manifest("clip-embedding")], errors=[]), repo
    )
    await enable_plugin("clip-embedding", repo)

    enabled = await list_enabled_manifests(DiscoveryResult(manifests=[], errors=[]), repo)

    assert enabled == []
