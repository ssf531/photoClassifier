from collections.abc import Callable, Sequence
from dataclasses import dataclass

from core.domain.plugins import Capability
from core.infrastructure.db.ai_result_models import AiResult

TagValue = str | int | list[str]

_LIGHTROOM_KEYWORD_ROOT = "AI Tags"


def _caption_and_rating_tags(
    ai_results: Sequence[AiResult], rating: int | None
) -> dict[str, TagValue]:
    tags: dict[str, TagValue] = {}
    for result in ai_results:
        if result.capability == Capability.CAPTION.value:
            caption = result.payload.get("caption")
            if caption:
                tags["Description"] = caption
    if rating is not None:
        tags["Rating"] = rating
    return tags


def _tag_labels(ai_results: Sequence[AiResult]) -> list[str]:
    for result in ai_results:
        if result.capability == Capability.TAG.value:
            labels = [tag["label"] for tag in result.payload.get("tags", [])]
            if labels:
                return labels
    return []


def _base_tags(ai_results: Sequence[AiResult], rating: int | None) -> dict[str, TagValue]:
    tags = _caption_and_rating_tags(ai_results, rating)
    labels = _tag_labels(ai_results)
    if labels:
        tags["Subject"] = labels
    return tags


def _lightroom_tags(ai_results: Sequence[AiResult], rating: int | None) -> dict[str, TagValue]:
    """Writes tags as `lr:hierarchicalSubject` (ExifTool tag name
    `HierarchicalSubject`) instead of a flat `dc:subject` list -- the
    format Lightroom actually reads as nested keywords, each entry being
    a single pipe-delimited string (verified against a real installed
    ExifTool: `-HierarchicalSubject+=AI Tags|dog` round-trips through
    both write and `-json` read as one list item, "AI Tags|dog").
    """
    tags = _caption_and_rating_tags(ai_results, rating)
    labels = _tag_labels(ai_results)
    if labels:
        tags["HierarchicalSubject"] = [f"{_LIGHTROOM_KEYWORD_ROOT}|{label}" for label in labels]
    return tags


@dataclass(frozen=True)
class ExportPreset:
    name: str
    build_tags: Callable[[Sequence[AiResult], int | None], dict[str, TagValue]]


DEFAULT_PRESET = ExportPreset(name="default", build_tags=_base_tags)
LIGHTROOM_PRESET = ExportPreset(name="lightroom", build_tags=_lightroom_tags)

_PRESETS_BY_NAME = {preset.name: preset for preset in (DEFAULT_PRESET, LIGHTROOM_PRESET)}


class UnknownPresetError(Exception):
    pass


def get_preset(name: str) -> ExportPreset:
    preset = _PRESETS_BY_NAME.get(name)
    if preset is None:
        raise UnknownPresetError(f"unknown export preset: {name!r}")
    return preset
