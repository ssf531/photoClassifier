from core.domain.plugins import PluginManifest
from core.infrastructure.db.plugin_models import Plugin
from core.infrastructure.plugin_discovery import DiscoveryResult
from core.infrastructure.plugin_repository import PluginRepository

BUILTIN_SOURCE = "builtin"


class UnknownPluginError(Exception):
    pass


async def sync_discovered_plugins(
    discovery: DiscoveryResult, repo: PluginRepository
) -> list[Plugin]:
    """Reconcile discovered manifests against persisted state (SDD §8.3 v1 lifecycle:
    discover -> instantiate enabled providers). A manifest seen for the first time is
    persisted disabled by default (opt-in); a manifest already known keeps its
    persisted enabled flag while its descriptive metadata is refreshed.
    """
    synced: list[Plugin] = []
    for manifest in discovery.manifests:
        existing = await repo.get(manifest.id)
        enabled = existing.enabled if existing is not None else False
        synced.append(
            await repo.upsert(
                Plugin(
                    id=manifest.id,
                    name=manifest.name,
                    capability_types=manifest.capability.value,
                    version=manifest.version,
                    source=BUILTIN_SOURCE,
                    enabled=enabled,
                )
            )
        )
    return synced


async def enable_plugin(plugin_id: str, repo: PluginRepository) -> Plugin:
    plugin = await repo.get(plugin_id)
    if plugin is None:
        raise UnknownPluginError(plugin_id)
    plugin.enabled = True
    return await repo.upsert(plugin)


async def disable_plugin(plugin_id: str, repo: PluginRepository) -> Plugin:
    plugin = await repo.get(plugin_id)
    if plugin is None:
        raise UnknownPluginError(plugin_id)
    plugin.enabled = False
    return await repo.upsert(plugin)


async def list_enabled_manifests(
    discovery: DiscoveryResult, repo: PluginRepository
) -> list[PluginManifest]:
    """The manifests a provider host should instantiate: those discovered on disk
    this run *and* persisted as enabled.
    """
    enabled_ids = {plugin.id for plugin in await repo.list_enabled()}
    return [manifest for manifest in discovery.manifests if manifest.id in enabled_ids]
