from collections.abc import Mapping
from typing import Any

from core.domain.plugins import Capability


class UnresolvedCapabilityError(Exception):
    pass


class ProviderRegistry:
    """Resolves capability -> provider for in-process (`entry_point="inproc"`)
    providers (SDD §8.0/ADR-0004): the whole of v1's "plugin host" is this lookup,
    since v1 has exactly one enabled provider per capability and no subprocess/RPC
    transport to route through. Constructed from already-instantiated providers;
    deciding *which* manifests are enabled is `plugin_lifecycle.list_enabled_manifests`.
    """

    def __init__(self, providers: Mapping[Capability, Any]) -> None:
        self._providers = dict(providers)

    def get_provider(self, capability: Capability) -> Any:
        try:
            return self._providers[capability]
        except KeyError:
            raise UnresolvedCapabilityError(capability.value) from None

    def capabilities(self) -> frozenset[Capability]:
        return frozenset(self._providers)
