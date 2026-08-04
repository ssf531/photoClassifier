# Writing an AI capability provider

v1 ships exactly one "plugin host": in-process `Protocol`-typed providers
(ADR-0004). There is no subprocess/RPC transport and no third-party plugin
loading — v1's plugin system exists to make each capability swappable, not
to run untrusted third-party code. There *is* a permission-approval step
in the Plugins UI (`PluginsPage.tsx`): enabling a plugin that declares
`permissions` in its manifest shows what it's asking for and requires an
explicit Approve click first (SDD §8.3) — every built-in provider today
declares `permissions = ["read:image_bytes"]`, so this dialog appears on
every enable action, even though nothing untrusted is actually running yet.
Out-of-process hosting (TASK-039) and a stable gRPC contract (TASK-038)
are both deferred to v2.

## The moving parts

1. **A capability Protocol** (`src/core/domain/providers.py`) — one per
   `Capability` (`embedding`, `caption`, `tag`, `quality`; duplicate
   detection doesn't take this shape, see below). Every result DTO (e.g.
   `CaptionResult`) carries `provider_id`, `model_version`, `confidence`,
   and `raw_payload: dict[str, Any]` so the Analysis Pipeline can persist
   any provider's output generically without knowing its capability-specific
   shape.
2. **A `plugin.toml` manifest** (`src/core/plugins/<id>/plugin.toml`) —
   declares identity, the capability it provides, and compatibility:

   ```toml
   [plugin]
   id = "clip-vit-base-patch32"
   name = "CLIP Embedding Provider"
   version = "1.0.0"
   capability = "embedding"          # embedding | caption | tag | quality | duplicate
   entry_point = "inproc"            # the only value v1 supports
   runtime = "python"
   permissions = ["read:image_bytes"]
   model_source = "download"         # bundled | download | user_supplied
   model_filename = "vision_model_quantized.onnx"

   [compatibility]
   core_api_version = ">=1.0,<2.0"
   ```

   `discover_plugins()` (`core/infrastructure/plugin_discovery.py`) parses
   every `plugins_dir/*/plugin.toml`, validates it against `PluginManifest`,
   and checks `compatibility.core_api_version` against the running core's
   `CORE_API_VERSION` — an incompatible or malformed manifest is recorded as
   a `DiscoveryError`, not a startup crash.
3. **A provider implementation** — any class satisfying the capability's
   `Protocol` (structural typing: no base class to inherit, no registration
   decorator). See `caption_provider.py`/`clip_embedding_provider.py` for
   the ONNX Runtime pattern this repo uses: lazy model loading in
   `_ensure_loaded()`, an `is_available()` check driven by
   `model_acquisition.is_model_available()`, and heavy imports
   (`onnxruntime`, `tokenizers`) deferred to first use (SDD §3.14) rather
   than imported at module scope.
4. **Wiring into `composition.py`** — this is the part that's still manual
   in v1: instantiate the provider, and if its manifest is enabled (checked
   via `list_enabled_manifests()`) and `is_available()` returns true, add it
   to the `capability_providers` dict passed to `ProviderRegistry`. A
   manifest existing and being enabled in the Plugins UI is necessary but
   not sufficient — `composition.py` still needs a line instantiating and
   registering the concrete provider class. There is no dynamic
   class-loading from the manifest in v1.

## Capabilities that don't fit the Protocol shape

- **Duplicate detection** (`duplicate_detection.py`) takes a batch of
  `DuplicateCandidate`s and returns `DuplicateGroupResult`s rather than
  running per-photo — it's a grouping operation, not a per-image inference
  call, so it isn't registered through `ProviderRegistry`/`AnalysisPipeline`
  the same way.
- **Tagging** (`tag_provider.py`) is a derived provider: it depends on an
  `EmbeddingProvider` (CLIP) rather than shipping its own model, computing
  zero-shot tag scores against a versioned label vocabulary
  (`tag_vocabulary_v1.json`) via cosine similarity (ADR-0006). If you're
  adding a genuinely new tagging approach, decide first whether it's really
  a new `EmbeddingProvider` or a new vocabulary against the existing one,
  since a second full tagging model was explicitly rejected for v1.

## Model acquisition and degraded mode

Providers whose `model_source` is `download` implement
`ensure_downloaded(client)` (see `caption_provider.py`) fetching the files
named by their manifest from a fixed model repo URL into
`models_dir()/<provider_id>/`. `is_available()` must return `False` until
every required file is present — `_ensure_loaded()` should only be called
once availability is confirmed. A provider whose model isn't downloaded
yet is not an error: `composition.py` simply omits it from
`capability_providers`, and any job needing it fails with
`UnresolvedCapabilityError` → recorded as the `capability_unavailable`
`job_item.error_code` (SDD §16.3), surfaced later in the Problems view
with a retry action once the model becomes available. This is the "works
with zero models" guarantee (SDD §16.4) — never make provider construction
itself fail because a model isn't present.

## Testing a new provider

- Unit-test against the `Protocol` with fake dependencies — no real model
  inference (see `tests/unit/core/infrastructure/test_tag_provider.py` for
  the derived-provider pattern, mocking the `EmbeddingProvider` it depends
  on).
- If the provider does real ONNX inference, add a small, fast integration
  test gated on the model actually being present in the local cache (see
  `test_caption_provider_real_model.py`/`test_clip_embedding_real_model.py`
  — both skip automatically when the cache is empty, so CI doesn't need a
  model download).
