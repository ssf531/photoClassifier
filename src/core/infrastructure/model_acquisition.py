import shutil
from collections.abc import Sequence
from pathlib import Path

import httpx

from core.domain.plugins import (
    AvailabilityStatus,
    Capability,
    CapabilityAvailability,
    ModelSource,
    PluginManifest,
)


class ModelSourceMissingError(Exception):
    pass


def resolve_model_path(cache_dir: Path, provider_id: str, filename: str) -> Path:
    return cache_dir / provider_id / filename


def is_model_available(cache_dir: Path, provider_id: str, filename: str) -> bool:
    return resolve_model_path(cache_dir, provider_id, filename).is_file()


def import_local_model(source_path: Path, cache_dir: Path, provider_id: str, filename: str) -> Path:
    """Offline-import path (SDD §16.4): copy a user-supplied model file into the
    cache, landing it in the same place a download would -- the two paths
    "produce identical results" from here on, so availability checks never
    need to distinguish how a model arrived.
    """
    if not source_path.is_file():
        raise ModelSourceMissingError(str(source_path))

    destination = resolve_model_path(cache_dir, provider_id, filename)
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destination.with_name(destination.name + ".tmp")
    shutil.copyfile(source_path, tmp_path)
    tmp_path.replace(destination)
    return destination


async def download_model(
    url: str, cache_dir: Path, provider_id: str, filename: str, *, client: httpx.AsyncClient
) -> Path:
    """Streamed, non-blocking download to the model cache (SDD §16.4): a
    multi-gigabyte file is written incrementally, never buffered whole in
    memory, and only replaces the final path once fully written.
    """
    destination = resolve_model_path(cache_dir, provider_id, filename)
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destination.with_name(destination.name + ".tmp")

    async with client.stream("GET", url) as response:
        response.raise_for_status()
        with tmp_path.open("wb") as f:
            async for chunk in response.aiter_bytes():
                f.write(chunk)

    tmp_path.replace(destination)
    return destination


def compute_capability_availability(
    manifests: Sequence[PluginManifest], cache_dir: Path
) -> dict[Capability, CapabilityAvailability]:
    """Capability availability (SDD §16.4), computed at startup and whenever
    models change. Bundled models need nothing acquired; download/user-
    supplied models are available once their file exists in the cache --
    per `import_local_model`'s docstring, both acquisition paths look
    identical from here.
    """
    availability: dict[Capability, CapabilityAvailability] = {}
    for manifest in manifests:
        if manifest.model_source == ModelSource.BUNDLED:
            availability[manifest.capability] = CapabilityAvailability(
                status=AvailabilityStatus.AVAILABLE
            )
            continue

        if manifest.model_filename is None:
            availability[manifest.capability] = CapabilityAvailability(
                status=AvailabilityStatus.UNAVAILABLE,
                reason="plugin manifest declares no model_filename",
            )
            continue

        if is_model_available(cache_dir, manifest.id, manifest.model_filename):
            availability[manifest.capability] = CapabilityAvailability(
                status=AvailabilityStatus.AVAILABLE
            )
        else:
            availability[manifest.capability] = CapabilityAvailability(
                status=AvailabilityStatus.UNAVAILABLE, reason="model not yet acquired"
            )

    return availability
