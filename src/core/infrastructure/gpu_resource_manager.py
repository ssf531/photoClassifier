import asyncio
from collections.abc import Sequence

import onnxruntime

PREFERRED_EXECUTION_PROVIDER_ORDER = (
    "CUDAExecutionProvider",
    "DmlExecutionProvider",
    "CPUExecutionProvider",
)


class UnavailableExecutionProviderError(Exception):
    pass


class NoExecutionProviderAvailableError(Exception):
    pass


def select_execution_provider(
    *, override: str | None = None, available: Sequence[str] | None = None
) -> str:
    """Choose an ONNX Runtime execution provider once at startup: CUDA, then
    DirectML, then CPU, overridable in Settings (ADR-0009). CPU-only is not a
    fallback branch -- it's the same selection landing on the only provider
    present, which is why it runs by default in CI where no GPU exists.
    """
    providers = list(available) if available is not None else onnxruntime.get_available_providers()

    if override is not None:
        if override not in providers:
            raise UnavailableExecutionProviderError(override)
        return override

    for candidate in PREFERRED_EXECUTION_PROVIDER_ORDER:
        if candidate in providers:
            return candidate

    raise NoExecutionProviderAvailableError(str(providers))


def create_inference_semaphore() -> asyncio.Semaphore:
    """At most one inference call runs at a time, regardless of device (ADR-0009):
    a single global semaphore rather than per-device slots, since v1 targets a
    single-user desktop with at most one GPU. Constructed once by the
    composition root, per ADR-0008 (no module-level singletons).
    """
    return asyncio.Semaphore(1)
