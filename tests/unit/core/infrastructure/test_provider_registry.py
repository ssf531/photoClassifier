import pytest

from core.domain.plugins import Capability
from core.infrastructure.provider_registry import ProviderRegistry, UnresolvedCapabilityError


class _FakeEmbeddingProvider:
    pass


def test_get_provider_returns_the_registered_instance() -> None:
    provider = _FakeEmbeddingProvider()
    registry = ProviderRegistry({Capability.EMBEDDING: provider})

    assert registry.get_provider(Capability.EMBEDDING) is provider


def test_get_provider_raises_for_unregistered_capability() -> None:
    registry = ProviderRegistry({})

    with pytest.raises(UnresolvedCapabilityError, match="caption"):
        registry.get_provider(Capability.CAPTION)


def test_capabilities_reports_the_registered_set() -> None:
    registry = ProviderRegistry(
        {Capability.EMBEDDING: _FakeEmbeddingProvider(), Capability.TAG: _FakeEmbeddingProvider()}
    )

    assert registry.capabilities() == {Capability.EMBEDDING, Capability.TAG}
