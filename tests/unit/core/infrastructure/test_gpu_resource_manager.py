import asyncio

import pytest

from core.infrastructure.gpu_resource_manager import (
    NoExecutionProviderAvailableError,
    UnavailableExecutionProviderError,
    create_inference_semaphore,
    select_execution_provider,
)


def test_prefers_cuda_when_available() -> None:
    provider = select_execution_provider(
        available=["CUDAExecutionProvider", "CPUExecutionProvider"]
    )

    assert provider == "CUDAExecutionProvider"


def test_prefers_directml_over_cpu_when_no_cuda() -> None:
    provider = select_execution_provider(available=["DmlExecutionProvider", "CPUExecutionProvider"])

    assert provider == "DmlExecutionProvider"


def test_falls_back_to_cpu_when_nothing_else_available() -> None:
    provider = select_execution_provider(available=["CPUExecutionProvider"])

    assert provider == "CPUExecutionProvider"


def test_settings_override_wins_when_available() -> None:
    provider = select_execution_provider(
        override="CPUExecutionProvider",
        available=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )

    assert provider == "CPUExecutionProvider"


def test_settings_override_raises_when_not_available() -> None:
    with pytest.raises(UnavailableExecutionProviderError):
        select_execution_provider(
            override="CUDAExecutionProvider", available=["CPUExecutionProvider"]
        )


def test_raises_when_no_providers_at_all() -> None:
    with pytest.raises(NoExecutionProviderAvailableError):
        select_execution_provider(available=[])


def test_reads_real_onnxruntime_providers_by_default() -> None:
    # No `available` override: exercises the real onnxruntime.get_available_providers()
    # call. CPUExecutionProvider ships with every onnxruntime install, so this
    # must always resolve regardless of what hardware CI runs on (ADR-0009).
    provider = select_execution_provider()

    assert provider in (
        "CUDAExecutionProvider",
        "DmlExecutionProvider",
        "CPUExecutionProvider",
    )


async def test_inference_semaphore_allows_only_one_holder_at_a_time() -> None:
    semaphore = create_inference_semaphore()
    order: list[str] = []

    async def hold(name: str) -> None:
        async with semaphore:
            order.append(f"{name}-start")
            await asyncio.sleep(0.01)
            order.append(f"{name}-end")

    await asyncio.gather(hold("a"), hold("b"))

    # each holder's start/end pair must not interleave with the other's
    assert order in (
        ["a-start", "a-end", "b-start", "b-end"],
        ["b-start", "b-end", "a-start", "a-end"],
    )
