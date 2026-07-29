import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from core.domain.plugins import Capability
from core.domain.providers import ImageRef
from core.infrastructure.ai_result_repository import AiResultRepository
from core.infrastructure.provider_registry import ProviderRegistry, UnresolvedCapabilityError

CAPABILITY_UNAVAILABLE = "capability_unavailable"
PROVIDER_ERROR = "provider_error"


class GenericCapabilityResult(Protocol):
    """Structural shape every `*Result` DTO satisfies (SDD §6.1), letting the
    pipeline persist any capability's result without knowing its specific
    shape."""

    provider_id: str
    model_version: str
    confidence: float
    raw_payload: dict[str, Any]


CapabilityInvoker = Callable[[Any, ImageRef], Awaitable[GenericCapabilityResult]]


@dataclass(frozen=True)
class CapabilityFailure:
    photo_id: uuid.UUID
    capability: Capability
    error_code: str
    error_message: str


@dataclass
class BatchReport:
    succeeded: int = 0
    failures: list[CapabilityFailure] = field(default_factory=list)


class AnalysisPipeline:
    """Runs enabled AI capabilities over a batch of photos (SDD §6.2): for
    each (photo, capability), resolve the provider, invoke it, and persist
    the result. A provider that raises, or a capability with no registered
    provider, fails only that (photo, capability) pair and is recorded --
    the batch continues (ADR-0004's fault isolation; SDD §16.3 taxonomy).

    Each capability's invoker (how to call its specific Protocol method) is
    supplied by the caller rather than hardcoded here, since v1 providers
    have differently-named capability methods (`assess`, `caption`, `tag`, ...).
    """

    def __init__(
        self,
        providers: ProviderRegistry,
        ai_results: AiResultRepository,
        invokers: Mapping[Capability, CapabilityInvoker],
    ) -> None:
        self._providers = providers
        self._ai_results = ai_results
        self._invokers = invokers

    async def run_batch(
        self, images: Sequence[ImageRef], capabilities: Sequence[Capability]
    ) -> BatchReport:
        report = BatchReport()
        for image in images:
            for capability in capabilities:
                await self._run_one(image, capability, report)
        return report

    async def _run_one(self, image: ImageRef, capability: Capability, report: BatchReport) -> None:
        try:
            provider = self._providers.get_provider(capability)
        except UnresolvedCapabilityError as exc:
            report.failures.append(
                CapabilityFailure(image.photo_id, capability, CAPABILITY_UNAVAILABLE, str(exc))
            )
            return

        invoker = self._invokers[capability]
        try:
            result = await invoker(provider, image)
        except Exception as exc:
            report.failures.append(
                CapabilityFailure(image.photo_id, capability, PROVIDER_ERROR, str(exc))
            )
            return

        await self._ai_results.record_result(
            photo_id=image.photo_id,
            plugin_id=result.provider_id,
            capability=capability.value,
            model_version=result.model_version,
            payload=result.raw_payload,
            confidence=result.confidence,
        )
        report.succeeded += 1
