import asyncio
import json
from pathlib import Path

from core.infrastructure.clip_embedding_provider import ClipEmbeddingProvider
from core.infrastructure.tag_provider import DEFAULT_VOCABULARY_PATH, TaggingProvider


def test_default_vocabulary_loads_a_non_empty_versioned_label_set() -> None:
    vocabulary = json.loads(DEFAULT_VOCABULARY_PATH.read_text(encoding="utf-8"))

    assert vocabulary["version"]
    assert len(vocabulary["labels"]) > 10
    assert len(vocabulary["labels"]) == len(set(vocabulary["labels"]))


def test_is_available_delegates_to_the_embedding_provider(tmp_path: Path) -> None:
    embedding_provider = ClipEmbeddingProvider(tmp_path, asyncio.Semaphore(1))
    provider = TaggingProvider(embedding_provider)

    assert provider.is_available() is False


def test_model_version_combines_embedding_and_vocabulary_versions(tmp_path: Path) -> None:
    embedding_provider = ClipEmbeddingProvider(tmp_path, asyncio.Semaphore(1))
    provider = TaggingProvider(embedding_provider)

    assert provider.model_version == f"{embedding_provider.model_version}+tag-vocab-v1"


def test_custom_vocabulary_path_is_honored(tmp_path: Path) -> None:
    vocab_path = tmp_path / "custom_vocab.json"
    vocab_path.write_text(
        json.dumps({"version": "custom-vocab-v1", "labels": ["alpha", "beta"]}),
        encoding="utf-8",
    )
    embedding_provider = ClipEmbeddingProvider(tmp_path, asyncio.Semaphore(1))

    provider = TaggingProvider(embedding_provider, vocabulary_path=vocab_path)

    assert provider.model_version == f"{embedding_provider.model_version}+custom-vocab-v1"
