# AI Development Guide

Version: 1.0
Date: 2026-07-29
Status: Normative. Where this document conflicts with an older document, this document wins for conventions and terminology; the ADR register wins for decisions.

**Read this before your first task, then keep it open.** This document is the working agreement for everyone — human or agent — writing code in this repository. It replaces §11 of the Implementation Plan.

Reading order for a new contributor:

1. This document (conventions, glossary, working agreement)
2. `Architecture_Decision_Records_v1.md` — what was decided and why, especially the five reversals
3. Your assigned task's block in `Local_AI_Photo_Intelligence_Implementation_Plan_v1.md`
4. Only the SDD sections your task references

Do **not** read the whole SDD before starting a task. It is 90KB, roughly a third of it is deferred v2 design, and reading it end-to-end is the main way contributors end up implementing v2 machinery by accident.

---

## 1. The five things most likely to go wrong

Ordered by how often they happen and how expensive they are to undo.

| # | Failure | Rule |
|---|---|---|
| 1 | **Implementing deferred v2 design as if it were v1.** The SDD contains a full gRPC plugin runtime, a GPU resource manager, a file-move engine, and a LanceDB integration. None are v1. | If a section heading says **(deferred — v2 design)**, or an ADR marks it Deferred, do not implement it. Check the ADR register when in doubt. |
| 2 | **Inventing a second name for an existing concept**, producing `Photo`, `PhotoRecord`, `FileEntry`, and `ImageRef` for one entity. | Use §2's glossary verbatim. Never introduce a synonym. |
| 3 | **Silently widening scope** — refactoring adjacent code, adding an unrequested option, "cleaning up while I'm here." | Produce exactly the task's stated Outputs. File anything else as a follow-up; note it in the PR description. |
| 4 | **Stubbing around an unmerged dependency.** | Dependencies are a hard gate. If a dependency is not merged, stop and say so — do not write a placeholder you intend to replace. |
| 5 | **Marking a task done with a `TODO`, a skipped test, or a `NotImplementedError` on a path the task claims to deliver.** | If the task cannot be finished at its stated size, it was mis-scoped. Say that instead of shipping a partial. |

---

## 2. Normative glossary

**One concept, one name.** These names are used identically in code, database, API, UI, and documents. Earlier documents used some of these interchangeably; this table is now authoritative.

| Term | Meaning | Code identifier | DB table/column |
|---|---|---|---|
| **Photo** | One image file known to the application. The single core entity. | `Photo`, `photo_id: PhotoId` | table `photo`, PK `id` |
| **Library Root** | A user-configured folder tree that is scanned. | `LibraryRoot`, `library_root_id` | table `library_root` |
| **Metadata** | Camera/technical data read from the file (EXIF/IPTC/XMP). Never AI-derived, never user-authored. | `PhotoMetadata` | table `metadata` |
| **AI Result** | One capability's output for one photo from one provider version. Append-only. | `AiResult` | table `ai_result` |
| **User Data** | Rating, favourite, notes — authored by the user. | `UserData` | table `user_data` |
| **Capability** | A kind of AI analysis: `embedding`, `caption`, `tag`, `duplicate`, `quality`. (v1 set.) | `Capability` enum | `ai_result.capability` |
| **Provider** | A class implementing one capability. | `CaptionProvider`, … | table `plugin` |
| **Analysis Pipeline** | The component that runs enabled providers over photos and persists results. Not "AI Pipeline", not "AI Analysis Pipeline". | `AnalysisPipeline` | — |
| **Job / Job Item** | A durable unit of background work and its per-photo elements. | `Job`, `JobItem` | tables `job`, `job_item` |
| **Collection** | A database-only grouping of photos. Never a folder. | `Collection` | table `collection` |
| **Smart Collection** | A collection whose membership is a saved `SearchQuery`, evaluated live. | `SmartCollection` | `smart_collection_rule` |
| **Embedding Index** | The interface over vector storage. Never name the backing store in application code. | `EmbeddingIndex` | `embedding_ref.vector_key` |
| **Text Search Index** | The interface over full-text search. | `TextSearchIndex` | FTS5 tables |
| **Sidecar** | An `.xmp` file beside a photo. Export/interop format only, never a data source of truth. | — | `xmp_export_record` |

Forbidden synonyms — never introduce these: `Image`, `Picture`, `Asset`, `PhotoRecord`, `FileEntry`, `ImageRef`, `MediaItem` for **Photo**; `Album`, `Folder`, `Group`, `Set` for **Collection**; `Model`, `Engine`, `Backend`, `Analyzer` for **Provider**; `Tags`/`Keywords` used interchangeably (a tag is an AI Result; a keyword is an XMP export field).

Casing: `snake_case` for Python and SQL, `camelCase` for TypeScript, `PascalCase` for types in both. The API speaks `snake_case` JSON; the generated TypeScript client is the only place the boundary is crossed, and it is generated, not hand-written.

---

## 3. What v1 is

Repeat this back to yourself before starting any task. If your task seems to need something not on this list, you have misread the task.

**v1 is:** one process. Python + TypeScript. One SQLite file (relational + `sqlite-vec` + FTS5). In-process AI providers. CLIP embeddings, captions, tags-from-CLIP, pHash duplicates, sharpness. Metadata / keyword / semantic / similar-image search. Collections and smart collections. XMP sidecar export and copy-to-folder. A Windows installer.

**v1 is not:** Rust or Tauri. gRPC or protobuf. LanceDB or Tantivy. A DI framework. Process pools. A GPU scheduler. Third-party plugins. Connectors to Immich, PhotoPrism, Lightroom, or digiKam. OCR, landmark, scene, colour, or aesthetic analysis. **Moving, renaming, or deleting any original file.**

The last item is a hard product guarantee, not a scheduling choice — see ADR-0007.

---

## 4. Architectural rules

### 4.1 Dependency direction

```
api  →  application  →  domain  ←  infrastructure
```

`domain` holds entities and `Protocol` interfaces and imports nothing from the other three. `infrastructure` implements domain interfaces. `application` orchestrates use-cases against interfaces only. `api` translates HTTP to use-case calls and holds no logic.

A `from infrastructure import ...` inside `domain` or `application` is a defect regardless of what it makes convenient. This is enforced by an import-linter rule in CI.

### 4.2 Interfaces are contracts

When your task's Outputs include an interface others depend on, the signatures in the SDD or the plan are exact. Do not rename parameters, reorder them, change return types, or "improve" the shape — another contributor is implementing against that signature in parallel, possibly right now.

### 4.3 Composition, not injection

One module (`composition.py`) constructs concrete classes. Everything else receives collaborators as constructor arguments typed as `Protocol`s. No DI framework, no service locator, no module-level singletons (ADR-0008).

```python
# domain/providers.py
class CaptionProvider(Protocol):
    async def caption(self, photo: PhotoRef) -> CaptionResult: ...

# application/analysis_pipeline.py
class AnalysisPipeline:
    def __init__(self, providers: ProviderRegistry, results: AiResultRepository) -> None:
        self._providers = providers          # Protocol, not a concrete class
        self._results = results

# composition.py — the only module that names concrete implementations
pipeline = AnalysisPipeline(
    providers=ProviderRegistry(load_builtin_providers(settings)),
    results=SqliteAiResultRepository(write_connection),
)
```

### 4.4 Writes and concurrency

- **All database writes happen on the asyncio event loop through the single write connection.** Reads use pooled read-only connections. `PRAGMA busy_timeout` is set. Do not add a write queue, an actor, or a second write connection (SDD §5.5).
- **CPU-bound work uses `asyncio.to_thread`.** Never `ProcessPoolExecutor`, never bare `threading.Thread` (ADR-0005).
- **Inference is guarded by the single global semaphore** exposed by the composition root. Do not create another (ADR-0009).
- **Transactions are per use-case, not per row.** A scan chunk or an AI batch is one transaction.

### 4.5 Never materialise an unbounded result set

Any query that could return "all photos" returns an `AsyncIterator` or takes explicit `limit`/`offset`. At a million photos, `list(all_photos())` is a bug even when it happens to work on your fixture. Repository `list_*` methods must require pagination arguments rather than defaulting to unbounded.

### 4.6 Original files are read-only

Only two modules may write to the filesystem outside the app's own data directories: the XMP sidecar exporter (creates `.xmp` files) and the copy-to-folder exporter (creates new copies). No other module may open a path under a library root in a write mode, and nothing in v1 may call `os.rename`, `os.remove`, `shutil.move`, `Path.unlink`, or `Path.rename` against a library path. CI enforces this with a targeted check; if your task appears to require it, the task is wrong — stop and raise it (ADR-0007).

---

## 5. Conventions

### 5.1 Types and errors

- Full type annotations on every function. `mypy --strict` on `src/core` is a merge gate.
- Domain errors are typed exceptions in `domain/errors.py`, each carrying a stable `error_code` string. Never raise bare `Exception`, and never return `None` to signal failure.
- Every failure that concerns a single photo is classified per SDD §16.3 (`transient` / `item_permanent` / `capability_permanent` / `fatal`). The class determines retry behaviour, so choosing it is part of the task, not an afterthought.
- Never swallow an exception without logging it with context.

### 5.2 Logging

`structlog`, structured key-values, never f-string prose:

```python
log.info("analysis.item.completed", photo_id=str(photo_id), capability="caption",
         provider="blip2-base@1", duration_ms=elapsed)
```

Event names are `lowercase.dotted.past_tense`. Bind `job_id` and `photo_id` once at the top of a work item so nested calls inherit them. Never log a full filesystem path at `info` or above — paths are personal data (they contain names); log `photo_id` instead and let the diagnostics bundle handle paths with consent.

### 5.3 Paths and time

- Paths are `pathlib.Path` in code, root-relative with `/` separators in the database, `\\?\`-prefixed when opening on Windows. Never build a path with string concatenation (ADR-0010).
- `captured_at_local` is authoritative for all date display and date-range search. Never infer a timezone offset (ADR-0011).
- All other timestamps (`created_at`, `updated_at`) are UTC.

### 5.4 Database changes

Every schema change is an Alembic migration in the same PR as the code using it. Migrations must be a no-op on an empty database and correct from the previous revision; both are tested in CI. Pre-1.0 you may assume a derived table can be rebuilt rather than migrated — but `user_data`, `collection`, and `collection_item` hold data the user cannot recreate and must always be migrated properly, never dropped.

### 5.5 API and UI

- Endpoints are versioned under `/api/v1/`. Request and response models are Pydantic; no raw dicts cross the boundary.
- Adding or changing an endpoint means regenerating the TypeScript client **in the same PR**. A PR that changes the API without regenerating leaves the UI compiling against a contract that no longer exists.
- Long-running work returns a `job_id` immediately and reports progress over the WebSocket. No HTTP request waits on a scan or an analysis batch.

---

## 6. Testing

A task without tests is not done. Tests live in `tests/` mirroring `src/`.

| Test kind | Uses | Never |
|---|---|---|
| Unit | Fakes for every collaborator; in-memory SQLite where a DB is needed | Real models, real network, real ExifTool |
| Integration | A real temp SQLite file (WAL), real FTS5, real `sqlite-vec`, a tiny real model where a task's correctness depends on one | Large model downloads, GPU, external services |
| UI | Playwright against the built app | Screenshot-diffing (too brittle for this stage) |

Rules:

- **Test behaviour, not implementation.** Assert on the observable outcome, not on which private method ran.
- **No `pytest.mark.skip` in merged code**, and no test whose body is `assert True`. If a test cannot run in CI, it is not a test — document the manual check in the PR instead.
- **Fixtures over mocks for data.** `tests/fixtures/` holds real (small, license-clean) JPEG, RAW, and HEIC files, including deliberately malformed ones. Reach for a fake object only for behaviour, not to fabricate a photo.
- **Determinism.** No `Date.now()`-style dependence on wall-clock time or randomness; inject a clock and a seed.
- **Every bug fix starts with a failing test** that reproduces it.

---

## 7. Windows notes

You are developing on Windows 11. These bite here and not on Linux:

- **`MAX_PATH`.** Long paths need the manifest opt-in *and* `\\?\` prefixing. Test with a fixture path over 260 characters; it is the difference between a working scanner and one that silently skips files.
- **File locking.** Windows refuses to delete or rename an open file. Always use context managers, and expect `PermissionError` as a *transient* failure class when another application (a photo viewer, a sync client, an antivirus scanner) holds a handle.
- **Case-insensitive but case-preserving.** `Photo.JPG` and `photo.jpg` are the same file here and different files on Linux. Compare with the folded key; display the original case (ADR-0010).
- **CRLF.** `.gitattributes` normalises line endings. Never commit a file that flips every line.
- **Antivirus.** Real-time scanning makes bulk file reads dramatically slower. When a benchmark looks anomalous, check exclusions before optimising the code.
- **No `multiprocessing`** (ADR-0005) — spawn semantics are the reason.
- Prefer `pathlib` and `platformdirs` over any `win32` API. Windows is the first target, not an architectural assumption.

---

## 8. Pull request checklist

Copy into the PR description and complete honestly. This is the Definition of Done from the Implementation Plan, made operational.

```markdown
## TASK-NNN — <title>
Implements: SDD §<sections> | ADRs: <ADR-NNNN if relevant>

- [ ] Scope: only this task's stated Outputs. Out-of-scope items noted below, not included.
- [ ] Glossary: no new synonyms for existing concepts (AI Development Guide §2)
- [ ] v1 scope: nothing from a "(deferred — v2 design)" section implemented
- [ ] Interfaces: signatures match the SDD/plan exactly
- [ ] Layering: no infrastructure import in domain or application
- [ ] Tests: task's Suggested Tests implemented and passing; none skipped
- [ ] Full suite green; `mypy --strict` and `ruff` clean; `tsc --noEmit` clean if UI touched
- [ ] No TODO, no placeholder, no NotImplementedError on a delivered path
- [ ] Migration included if the schema changed; up-and-down tested
- [ ] TypeScript client regenerated if the API changed
- [ ] No write to any original file (only `.xmp` creation or copy-to-folder)
- [ ] Unbounded queries: none introduced
- [ ] Docs: new interfaces, config keys, and error codes documented at the point of change

### Out of scope, noticed while working
- <thing> → suggest follow-up task
```

---

## 9. Task brief template

A well-formed brief for an agent looks like this. If you are handed less than this, ask for the missing parts rather than guessing.

> **TASK-041 — CLIP embedding provider.**
> Read: `AI_Development_Guide_v1.md` §2–§4, SDD §6.1 (the `EmbeddingProvider` Protocol), ADR-0003 and ADR-0006.
> Merged and available: TASK-040 (provider registry), TASK-029 (`ai_result` repository).
> Deliver: `plugins/builtin/clip_embedding/` implementing `EmbeddingProvider.embed_image` and `embed_text` via ONNX Runtime, registered through the in-process registry, declaring `model_version="clip-vit-b32@1"`.
> Do **not**: add gRPC (ADR-0004), touch the GPU semaphore (ADR-0009), or implement tag derivation (that is TASK-043's scope, which consumes your output).
> Tests: determinism (same image twice, identical vector); a known-similar pair scores above a known-dissimilar pair on `tests/fixtures/similarity/`.
> Done when: FEAT-039's acceptance criteria pass and §8's checklist is complete.

Note what makes it work: an explicit read-list (not "read the SDD"), the merged prerequisites named, an explicit **do-not** list pointing at ADRs, and testable completion criteria. Ambiguity in a brief is resolved before implementation, never during.

---

## 10. When something is wrong

You will find genuine problems — that is expected and welcome. What matters is the response:

| Situation | Do |
|---|---|
| Two documents contradict each other | Follow the ADR register first, then this guide, then the SDD, then the plan. Flag the contradiction in your PR. |
| The task's design looks wrong | Implement it as specified **or** stop and raise it. Never quietly implement something different — a silent deviation surfaces as a mystery for the next contributor. |
| The task cannot be done at its stated size | Say so and propose a split. Do not ship a partial implementation. |
| A requirement is genuinely ambiguous and the documents are silent | Choose the narrower, safer reading — especially anything touching the filesystem — and state the assumption explicitly in the PR. |
| You want to add a dependency | Justify it in the PR against §3's v1 scope. New runtime dependencies need an ADR; new dev/test dependencies do not. |
| You find a real architectural problem | Write an ADR proposing the change. That is exactly what the register is for; ADR-0002 through ADR-0009 are all reversals of earlier decisions. |

Deviating from the plan is allowed. Deviating silently is not.
