import pytest

from core.domain.plugins import Capability
from core.infrastructure.db.ai_result_models import AiResult
from core.infrastructure.export_presets import (
    DEFAULT_PRESET,
    LIGHTROOM_PRESET,
    UnknownPresetError,
    get_preset,
)


def _ai_result(capability: str, payload: dict) -> AiResult:
    return AiResult(
        plugin_id="test-plugin",
        capability=capability,
        model_version="v1",
        payload=payload,
        confidence=1.0,
    )


def _caption_result(caption: str) -> AiResult:
    return _ai_result(Capability.CAPTION.value, {"caption": caption})


def _tag_result(*labels: str) -> AiResult:
    return _ai_result(
        Capability.TAG.value, {"tags": [{"label": label, "confidence": 0.9} for label in labels]}
    )


class TestDefaultPreset:
    def test_maps_caption_tags_and_rating_to_flat_xmp_fields(self) -> None:
        tags = DEFAULT_PRESET.build_tags(
            [_caption_result("a dog on the beach"), _tag_result("dog", "beach")], 4
        )

        assert tags == {
            "Description": "a dog on the beach",
            "Subject": ["dog", "beach"],
            "Rating": 4,
        }

    def test_omits_rating_when_none(self) -> None:
        tags = DEFAULT_PRESET.build_tags([_caption_result("hello")], None)

        assert "Rating" not in tags

    def test_returns_empty_dict_when_nothing_to_export(self) -> None:
        assert DEFAULT_PRESET.build_tags([], None) == {}


class TestLightroomPreset:
    def test_writes_tags_as_a_pipe_delimited_hierarchical_subject(self) -> None:
        tags = LIGHTROOM_PRESET.build_tags([_tag_result("dog", "beach")], None)

        assert tags == {"HierarchicalSubject": ["AI Tags|dog", "AI Tags|beach"]}

    def test_does_not_also_write_a_flat_subject_field(self) -> None:
        tags = LIGHTROOM_PRESET.build_tags([_tag_result("dog")], None)

        assert "Subject" not in tags

    def test_still_maps_caption_and_rating_like_the_default_preset(self) -> None:
        tags = LIGHTROOM_PRESET.build_tags([_caption_result("a dog on the beach")], 5)

        assert tags["Description"] == "a dog on the beach"
        assert tags["Rating"] == 5

    def test_returns_empty_dict_when_there_are_no_tags(self) -> None:
        assert LIGHTROOM_PRESET.build_tags([_caption_result("hello")], None) == {
            "Description": "hello"
        }


def test_get_preset_returns_the_named_preset() -> None:
    assert get_preset("default") is DEFAULT_PRESET
    assert get_preset("lightroom") is LIGHTROOM_PRESET


def test_get_preset_raises_for_an_unknown_name() -> None:
    with pytest.raises(UnknownPresetError):
        get_preset("nonexistent")
