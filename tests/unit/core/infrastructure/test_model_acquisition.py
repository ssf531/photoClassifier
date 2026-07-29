from pathlib import Path

import httpx
import pytest

from core.domain.plugins import (
    AvailabilityStatus,
    Capability,
    ModelSource,
    PluginCompatibility,
    PluginManifest,
)
from core.infrastructure.model_acquisition import (
    ModelSourceMissingError,
    compute_capability_availability,
    download_model,
    import_local_model,
    is_model_available,
    resolve_model_path,
)


def _manifest(
    plugin_id: str,
    capability: Capability,
    model_source: ModelSource,
    model_filename: str | None,
) -> PluginManifest:
    return PluginManifest(
        id=plugin_id,
        name=plugin_id,
        version="1.0.0",
        capability=capability,
        entry_point="inproc",
        runtime="python",
        model_source=model_source,
        model_filename=model_filename,
        compatibility=PluginCompatibility(core_api_version=">=1.0,<2.0"),
    )


def test_resolve_model_path_is_namespaced_by_provider(tmp_path: Path) -> None:
    path = resolve_model_path(tmp_path, "clip-embedding", "model.onnx")

    assert path == tmp_path / "clip-embedding" / "model.onnx"


def test_is_model_available_false_when_file_missing(tmp_path: Path) -> None:
    assert is_model_available(tmp_path, "clip-embedding", "model.onnx") is False


def test_is_model_available_true_once_file_exists(tmp_path: Path) -> None:
    target = resolve_model_path(tmp_path, "clip-embedding", "model.onnx")
    target.parent.mkdir(parents=True)
    target.write_bytes(b"weights")

    assert is_model_available(tmp_path, "clip-embedding", "model.onnx") is True


def test_import_local_model_copies_file_into_cache(tmp_path: Path) -> None:
    source = tmp_path / "source.onnx"
    source.write_bytes(b"weights")
    cache_dir = tmp_path / "cache"

    destination = import_local_model(source, cache_dir, "clip-embedding", "model.onnx")

    assert destination.is_file()
    assert destination.read_bytes() == b"weights"
    assert not destination.with_name(destination.name + ".tmp").exists()


def test_import_local_model_raises_when_source_missing(tmp_path: Path) -> None:
    with pytest.raises(ModelSourceMissingError):
        import_local_model(tmp_path / "does-not-exist.onnx", tmp_path / "cache", "p", "m.onnx")


async def test_download_model_streams_response_into_cache(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"weights-from-network")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        destination = await download_model(
            "https://example.invalid/model.onnx",
            tmp_path,
            "clip-embedding",
            "model.onnx",
            client=client,
        )

    assert destination.is_file()
    assert destination.read_bytes() == b"weights-from-network"
    assert not destination.with_name(destination.name + ".tmp").exists()


async def test_download_model_raises_on_http_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await download_model(
                "https://example.invalid/missing.onnx", tmp_path, "p", "m.onnx", client=client
            )


def test_bundled_capability_is_always_available(tmp_path: Path) -> None:
    manifest = _manifest("p", Capability.TAG, ModelSource.BUNDLED, model_filename=None)

    availability = compute_capability_availability([manifest], tmp_path)

    assert availability[Capability.TAG].status == AvailabilityStatus.AVAILABLE


def test_download_capability_unavailable_when_manifest_has_no_filename(tmp_path: Path) -> None:
    manifest = _manifest("p", Capability.EMBEDDING, ModelSource.DOWNLOAD, model_filename=None)

    availability = compute_capability_availability([manifest], tmp_path)

    assert availability[Capability.EMBEDDING].status == AvailabilityStatus.UNAVAILABLE
    assert availability[Capability.EMBEDDING].reason is not None


def test_download_capability_unavailable_when_model_file_missing(tmp_path: Path) -> None:
    manifest = _manifest(
        "clip-embedding", Capability.EMBEDDING, ModelSource.DOWNLOAD, model_filename="model.onnx"
    )

    availability = compute_capability_availability([manifest], tmp_path)

    assert availability[Capability.EMBEDDING].status == AvailabilityStatus.UNAVAILABLE
    assert availability[Capability.EMBEDDING].reason == "model not yet acquired"


def test_download_capability_available_once_model_file_exists(tmp_path: Path) -> None:
    manifest = _manifest(
        "clip-embedding", Capability.EMBEDDING, ModelSource.DOWNLOAD, model_filename="model.onnx"
    )
    resolve_model_path(tmp_path, "clip-embedding", "model.onnx").parent.mkdir(parents=True)
    resolve_model_path(tmp_path, "clip-embedding", "model.onnx").write_bytes(b"weights")

    availability = compute_capability_availability([manifest], tmp_path)

    assert availability[Capability.EMBEDDING].status == AvailabilityStatus.AVAILABLE
    assert availability[Capability.EMBEDDING].reason is None
