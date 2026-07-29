# Architecture Decision Records

Version: 1.0
Date: 2026-07-29
Origin: `Architecture_Audit_v1.md`

Each ADR records one decision with its context, the alternatives that were rejected, and the consequences accepted. ADRs marked **Supersedes** reverse a decision made in SDD v1.0; the original reasoning is preserved in each so that the reversal can itself be re-examined rather than rediscovered.

Status values: **Accepted** (in force), **Superseded** (replaced by a later ADR), **Deferred** (decided, but implementation scheduled for a later release).

When the repository gains its `docs/` structure (Implementation Plan TASK-001), these may be split into `docs/adr/NNNN-title.md` files. Numbering is permanent; ADRs are never edited after acceptance except to add a Superseded-by pointer.

| ADR | Title | Status | Supersedes |
|---|---|---|---|
| [0001](#adr-0001--python-312-for-the-core-application) | Python 3.12+ for the core application | Accepted | — (ratifies SDD §3.1) |
| [0002](#adr-0002--single-process-react-served-by-fastapi-in-a-pywebview-window) | Single process; React served by FastAPI in a pywebview window | Accepted | SDD §3.2, §2.2 |
| [0003](#adr-0003--one-sqlite-file-for-relational-vector-and-full-text-data) | One SQLite file for relational, vector, and full-text data | Accepted | SDD §3.5 |
| [0004](#adr-0004--v1-ai-providers-are-in-process-python-classes) | v1 AI providers are in-process Python classes | Accepted | SDD §8.3–8.5 (for v1) |
| [0005](#adr-0005--threads-not-process-pools-for-cpu-bound-image-work) | Threads, not process pools, for CPU-bound image work | Accepted | SDD §3.1, §3.9 |
| [0006](#adr-0006--derive-tags-from-clip-zero-shot-rather-than-a-dedicated-tagging-model) | Derive tags from CLIP zero-shot rather than a dedicated tagging model | Accepted | — |
| [0007](#adr-0007--v1-performs-no-destructive-file-operations) | v1 performs no destructive file operations | Accepted | — |
| [0008](#adr-0008--manual-composition-instead-of-a-dependency-injection-framework) | Manual composition instead of a dependency-injection framework | Accepted | SDD §3.12 (resolves) |
| [0009](#adr-0009--a-single-global-inference-semaphore-instead-of-a-gpu-scheduler) | A single global inference semaphore instead of a GPU scheduler | Accepted | SDD §6.3 (for v1) |
| [0010](#adr-0010--windows-path-handling-and-platformdirs-data-layout) | Windows path handling and platformdirs data layout | Accepted | — (fills a gap) |
| [0011](#adr-0011--naive-local-capture-time-is-authoritative) | Naive local capture time is authoritative | Accepted | — (fills a gap) |
| [0012](#adr-0012--heic-as-an-optional-component-raw-via-libraw) | HEIC as an optional component; RAW via LibRaw | Accepted | — (fills a gap) |

---

## ADR-0001 — Python 3.12+ for the core application

**Status:** Accepted (ratifies SDD §3.1 without change)

### Context

The application's central value is AI analysis of photographs. New vision models are released continuously, essentially always with PyTorch or ONNX weights and Python reference code. The orchestration core must also handle filesystem traversal, image decoding, metadata extraction, and database access at a scale of hundreds of thousands of files.

### Decision

Python 3.12 or later is the implementation language for the core application. CPU-intensive work is delegated to native-backed libraries (Pillow, rawpy/LibRaw, OpenCV, NumPy, ONNX Runtime) rather than written in Python loops.

### Alternatives considered

- **Rust** — better raw performance and memory safety, but the model ecosystem is far thinner. Every new model would require FFI wrapping or reimplementation, directly slowing the capability the product exists to deliver.
- **C#/.NET** — strong Windows integration, but ML.NET is a distant second to the Python ecosystem, and the choice would bias the design toward Windows-only.
- **Go** — excellent concurrency and single-binary distribution, minimal ML ecosystem; would end up calling Python anyway.

### Consequences

- Accepted: the GIL constrains in-process CPU parallelism (mitigated by ADR-0005), and distribution requires freezing the interpreter.
- Accepted: packaging is heavier than a compiled language's.
- Gained: the shortest possible path from "a model was released" to "the application supports it," which is the product's core competitive property.
- Gained: high AI-agent fluency, relevant because implementation is primarily agent-driven.

---

## ADR-0002 — Single process; React served by FastAPI in a pywebview window

**Status:** Accepted
**Supersedes:** SDD v1.0 §3.2 (Tauri 2.x shell) and §2.2 (three-process topology)

### Context

SDD v1.0 specified three processes in three languages: a Tauri/Rust shell supervising a Python core service, displaying a React UI, with a random port and a bearer token handed over via stdin. The stated first milestone is a working desktop application on Windows 11, developed largely by AI agents in VS Code.

Measured against that milestone, the Rust shell contributes: a third language and toolchain, a process-supervision and restart implementation, a stdin handshake protocol, and cross-runtime debugging — in exchange for a smaller installer and a native window host, both of which are release-polish properties rather than functional ones. The Implementation Plan's TASK-007 (shell, supervision, handshake) was sized L purely to make a window appear.

### Decision

For v1, the application runs as **one OS process**:

- Uvicorn/FastAPI runs on a background thread and owns all domain logic.
- The React UI is built to static assets and served by that same FastAPI application.
- A `pywebview` window (WebView2 on Windows, WebKitGTK on Linux, WKWebView on macOS) displays it.
- The server binds `127.0.0.1` on a fixed port; every request carries a per-launch bearer token held in memory. Because UI and API share a process, the token is never written to disk or passed through stdin.

Rust is removed from the project. v1 has two languages: Python and TypeScript.

### Alternatives considered

- **Tauri (the superseded decision)** — genuinely better installer size, native shell integration, and code-signing story. Retained as the recommended **v1.1** packaging upgrade: because the UI is already web technology speaking HTTP, adopting Tauri later replaces the window host only. Rejected for v1 because its benefits arrive at distribution time while its costs are paid on day one.
- **Electron** — same reasoning as Tauri, with a larger runtime footprint.
- **PySide6/Qt** — the strongest single-language alternative, and honestly the better choice for a team that will never want a web or mobile client: one process, one language, no HTTP layer at all, and `QListView` in icon mode is purpose-built for a very large thumbnail grid backed by a model. Rejected because the PRD anticipates a web interface and mobile companion, which Qt would require a second UI implementation to serve, and because AI-agent output quality for React is materially higher than for Qt — a first-order constraint given how this project will be built. **If those two premises change, this ADR should be revisited; Qt is not a worse architecture, it is a different bet.**
- **Serving the UI in the user's default browser instead of a window** — simplest of all, rejected because a photo application appearing as a browser tab, subject to the browser's own lifecycle and zoom, is not a desktop application.

### Consequences

- Accepted: thumbnails travel over loopback HTTP rather than being read directly from disk, requiring a caching endpoint (SDD §16.7). This is the approach Immich and PhotoPrism take; it is one small module.
- Accepted: `pywebview` has a smaller maintainer base than Tauri or Electron. Mitigated by the shell being roughly thirty lines and by the swap path above.
- Accepted: the v1 installer is larger than a Tauri build.
- Gained: one language and one toolchain removed; no process supervision, no restart logic, no handshake protocol.
- Gained: debugging is a single Python debugger plus WebView2 devtools, both natively supported in VS Code on Windows.
- Preserved: because the UI is a web client over HTTP, the future web interface, remote client, and NAS-server deployments in SDD §15 remain deployment changes rather than rewrites.

---

## ADR-0003 — One SQLite file for relational, vector, and full-text data

**Status:** Accepted
**Supersedes:** SDD v1.0 §3.5 (LanceDB as the primary vector store)

### Context

SDD v1.0 specified three storage engines: SQLite for relational data, LanceDB for vectors, FTS5 for full-text. Three engines mean three consistency stories, two separate "rebuild the derived index" paths, two backup procedures, and — visible in the ERD — a schema column named `lancedb_key`, placing a vendor name inside the domain model that the same document argues should be vendor-neutral.

LanceDB's advantages (IVF-PQ indexes, columnar layout, built-in versioning) materialise above roughly a million vectors. v1 targets a working desktop application; libraries in that range are the exception, not the norm.

### Decision

v1 stores everything in **one SQLite file**: relational tables, vector embeddings via the `sqlite-vec` extension, and full-text indexes via FTS5. The schema column recording a vector's key is named `vector_key`, not `lancedb_key`.

Application code depends on the `EmbeddingIndex` interface, never on `sqlite-vec` directly.

### Alternatives considered

- **LanceDB (the superseded decision)** — correct above roughly a million vectors and retained as the planned **v2** migration behind the unchanged `EmbeddingIndex` interface. Rejected for v1 because a second storage engine costs a second consistency and backup story before any user has a library large enough to benefit.
- **Offering both, selectable in Settings** — this is what SDD v1.0 actually proposed, and it is the worst option: it doubles the test matrix and makes behaviour configuration-dependent, for a choice no user is equipped to make.
- **Qdrant, Milvus, Weaviate** — server processes, incompatible with a zero-service desktop install.
- **FAISS** — an index without persistence or metadata storage; would require building the layer `sqlite-vec` provides.

### Consequences

- Accepted: a practical ceiling near one million vectors (recorded as TD-01), with a defined trigger for payment — a real library above ~750k photos, or p95 semantic search above 500 ms.
- Gained: a single-file database. Backup is a file copy; integrity check is one `PRAGMA`; recovery has one path.
- Gained: vector similarity and metadata filters can be combined in one SQL statement rather than intersecting result sets across engines.
- Gained: one fewer dependency to package, version, and freeze into the Windows installer.

---

## ADR-0004 — v1 AI providers are in-process Python classes

**Status:** Accepted for v1; the superseded design is **Deferred** to v2
**Supersedes:** SDD v1.0 §8.3–8.5 (gRPC transport, out-of-process host, lifecycle machinery) as v1 scope

### Context

SDD v1.0 specified a full plugin runtime: protobuf contracts per capability, generated gRPC stubs, a subprocess host with health-check polling, idle-timeout recycling, bounded crash-restart, and a permission model with user approval. Its stated hard rule is that third-party plugins always run out-of-process.

**Every provider in v1 is first-party and ships inside the application.** There is no untrusted code to isolate, and nothing to negotiate permissions with. The entire mechanism is therefore dead weight in v1, while costing four substantial tasks and being the plan's highest-complexity epic.

### Decision

v1 providers are plain Python classes implementing the capability `Protocol`s in SDD §6.1, declared in a `plugin.toml` manifest and instantiated in-process by a small registry. v1 has no gRPC, no protobuf, no subprocess host, no health-checking, no idle recycling, and no permission model.

Fault handling in v1: a provider that raises is caught by the Analysis Pipeline, which marks the affected `job_item` failed with an error code and continues. That is the whole of v1's isolation, and it is adequate for first-party code.

The **seam** is retained: capability `Protocol`s, manifest-declared providers, and a registry resolving capability → provider.

### Alternatives considered

- **Building the full gRPC runtime now (the superseded decision)** — retained verbatim as normative v2 design, to be built when the first third-party plugin exists or when a native library crash is observed in the wild. Rejected for v1 as machinery with no v1 consumer.
- **Subprocess isolation without gRPC** (e.g. `multiprocessing` with pickled calls) — cheaper than gRPC but inherits Windows spawn semantics (ADR-0005) and still buys isolation nobody needs yet.
- **No plugin abstraction at all in v1** — tempting, and it would save the registry and manifest. Rejected: the `Protocol` seam is what makes this ADR's deferral safe and reversible, and it costs almost nothing. Removing it would be over-simplifying past the point of value.

### Consequences

- Accepted: a crashing provider (typically a native library fault in a decoder or runtime) takes the application down. Recorded as TD-02, with the first observed occurrence as the trigger to build the deferred design.
- Accepted: third-party plugins are not supported in v1. This is stated in the PRD's release tiering rather than left as an implied capability.
- Gained: four tasks removed, two dependencies removed (`grpcio`, `protobuf`), a codegen step removed from the build, and the project's highest-complexity epic deferred.
- Gained: provider calls are ordinary function calls, so a breakpoint in a provider is reachable from the same debugger session as the caller.
- Preserved: adding out-of-process execution later means adding a second host behind the existing registry, not restructuring call sites.

---

## ADR-0005 — Threads, not process pools, for CPU-bound image work

**Status:** Accepted
**Supersedes:** SDD v1.0 §3.1 and §3.9 (`ProcessPoolExecutor` sized to `cpu_count - 1`)

### Context

Scanning, hashing, decoding, and thumbnailing are CPU-bound. SDD v1.0 specified a `ProcessPoolExecutor`, reasoning that the GIL prevents in-process parallelism.

That reasoning is incomplete. Pillow, rawpy/LibRaw, OpenCV, and NumPy release the GIL while executing native code — which is where essentially all of the time in these operations is spent. Threads therefore capture most of the available parallelism.

On Windows specifically, `multiprocessing` uses **spawn** rather than fork: each worker re-imports the module tree, all arguments must be picklable, database connections and open handles cannot be shared, and debugger attachment to workers is awkward. For a Windows-first project developed in VS Code, this is a recurring tax on exactly the code paths that need the most iteration.

### Decision

CPU-bound work runs via `asyncio.to_thread` (a bounded thread pool). `ProcessPoolExecutor` is not used in v1.

### Alternatives considered

- **`ProcessPoolExecutor` (the superseded decision)** — genuinely better for pure-Python CPU loops, which this application does not have. Remains available as a contained change if a profile shows GIL contention dominating rather than native execution.
- **A hybrid (threads for decode, processes for hashing)** — rejected as two concurrency models to reason about, for no measured benefit.
- **Native async file I/O** — orthogonal; the bottleneck is decode, not read.

### Consequences

- Accepted: if a future capability performs heavy work in pure Python (rather than in a native library), it will not scale across cores without revisiting this. Recorded implicitly under TD-05's profiling trigger.
- Accepted: a native-library crash in a worker thread takes the process down, where a process pool would have contained it. This is the same exposure as ADR-0004 and is tracked once, as TD-02.
- Gained: no spawn semantics, no pickling constraints, shared database connections, and breakpoints that work in worker code.
- Gained: simpler shutdown and cancellation, since threads share the process's state.

---

## ADR-0006 — Derive tags from CLIP zero-shot rather than a dedicated tagging model

**Status:** Accepted

### Context

The PRD requires tag generation. SDD v1.0 and the Implementation Plan specified a separate `TagProvider` with its own model, alongside the CLIP embedding provider already required for semantic search.

CLIP embeds images and text into one space. Scoring an image embedding against a precomputed set of label-text embeddings yields ranked tags with confidences — from an inference pass the pipeline already performs for search.

### Decision

v1 derives tags by scoring each photo's CLIP image embedding against a curated label vocabulary whose text embeddings are precomputed once. Tags are stored as ordinary `ai_result` rows with `capability='tag'`, indistinguishable in the schema from tags produced by any future dedicated model. The label vocabulary ships as a versioned data file, and its version forms part of the provider's declared `model_version`.

### Alternatives considered

- **A dedicated multi-label tagging model** — higher ceiling on tag quality and vocabulary size, and it remains available later as an additional provider for the same capability (the append-only result schema lets both coexist, per the PRD). Rejected for v1 as a second model download and a second provider for value the first model already largely delivers.
- **Extracting tags from generated captions with an LLM** — introduces a third model and makes tags depend on captioning being enabled.
- **No tags in v1** — rejected; tags are the primary browsing affordance and feed the built-in smart filters.

### Consequences

- Accepted: tag quality is bounded by the label vocabulary. A term absent from the vocabulary cannot be produced, whereas free-form models can surprise usefully. Mitigated by shipping a broad vocabulary and by making it a data file that can be extended without a code change.
- Accepted: vocabulary curation becomes a maintenance responsibility.
- Gained: one model download instead of two; one provider instead of two; tags and semantic search share one inference pass per photo.
- Preserved: adding a dedicated tagging provider later requires no schema change and no migration.

---

## ADR-0007 — v1 performs no destructive file operations

**Status:** Accepted — a permanent constraint on v1, not a scheduling convenience

### Context

The PRD requires that the application never move, rename, or delete files without explicit user confirmation, and SDD §10.2–10.3 specify a careful mechanism to honour that: staged operations, two-stage confirmation showing exact paths, atomic execution, OS trash by default, and a logged undo path.

That mechanism is correct, and it is also the only place in the entire system where a defect destroys something the user cannot recover. It was the highest-risk epic in the Implementation Plan.

Meanwhile the product's value proposition — understanding, searching, and organising a photo library — is fully deliverable without mutating a single original file.

### Decision

**v1 does not move, rename, or delete original files.** The only filesystem writes v1 performs are additive:

- XMP sidecar files (new files beside originals; originals untouched)
- Copying selected photos into a user-chosen folder (new files; sources untouched)

Organisation in v1 is entirely database-resident: virtual collections, smart collections, built-in filters, and review surfaces.

**v2 introduces** move, rename, archive, and optional delete, implemented exactly as SDD §10.2–10.3 specify. Those sections remain normative and must not be reinterpreted or simplified when implemented:

1. Staging and execution live in separate modules; the staging module contains no reference to any filesystem-mutating call.
2. A `file_operation_log` row at `status=confirmed` is the only route to execution.
3. Confirmation displays exact source and destination paths, file count, and total size.
4. Deletion goes to the OS trash by default; hard delete is a separately-worded opt-in.
5. Every operation type has a tested execute-then-undo round trip before the feature ships.

### Alternatives considered

- **Implementing move/copy/delete with the full safety machinery in v1 (the original plan)** — rejected for v1 because it front-loads the project's only irreversible-data-loss surface into the release with the least accumulated testing and the fewest real-world hours.
- **Implementing move and rename but not delete in v1** — rejected: an interrupted or wrongly-targeted move loses files just as thoroughly as a delete, so this halves the feature without halving the risk.
- **Implementing operations without the staged-confirmation machinery, relying on a simple confirm dialog** — rejected outright. This is the shortcut the constraint exists to prevent.

### Consequences

- Accepted: users cannot reorganise files on disk from within v1. They can identify what to act on (collections, duplicate review, recommendations) and export a selection, then act with their own file manager if they choose. This is a genuine limitation, and it is stated in the PRD's release tiering rather than left to be discovered.
- Accepted: the deferral must survive schedule pressure in v2 (recorded as R7). This ADR exists specifically so that a future implementer encounters the constraint as a decision with reasoning, not as an unexplained gap.
- Gained: eight tasks removed from v1, and the elimination of every code path in v1 capable of losing a user's photograph.
- Gained: the product's central guarantee becomes literally true in v1 — original files are exactly where the user left them.

---

## ADR-0008 — Manual composition instead of a dependency-injection framework

**Status:** Accepted
**Supersedes:** SDD v1.0 §3.12, which recommended `dependency-injector` while describing the choice as "a close call" and naming manual composition "an acceptable equivalent"

### Context

An approved design document must not leave a genuine either/or to the implementer. SDD v1.0 §3.12 did exactly that, and with multiple AI agents implementing tasks independently the predictable outcome is both patterns appearing in the same codebase.

### Decision

Dependency inversion is achieved with `Protocol` interfaces and **explicit manual composition in a single module** (`composition.py`). One module constructs concrete implementations and wires them together; every other module receives its collaborators as constructor arguments and depends only on `Protocol` types. Tests substitute fakes by calling the same constructors with different arguments.

`dependency-injector` is not a dependency of this project.

### Alternatives considered

- **`dependency-injector` (the superseded recommendation)** — declarative containers and test-time overrides without touching call sites. Rejected because the same test-time substitution is achieved by passing a different argument, which requires no framework, no new concept, and no dependency.
- **A service-locator or global registry** — rejected; hides dependencies rather than inverting them, and makes test isolation harder.
- **Framework-managed injection via FastAPI's `Depends`** — used for request-scoped concerns at the API boundary, where it is idiomatic. Not used for application-layer wiring, which must remain independent of the web framework.

### Consequences

- Accepted: `composition.py` grows as modules are added and must stay organised. This is visible, greppable coupling in one file — which is the point.
- Gained: one fewer dependency and one fewer concept; an agent reading any module sees its real collaborators in its constructor signature.
- Gained: the ambiguity that would have produced two competing patterns is closed.

---

## ADR-0009 — A single global inference semaphore instead of a GPU scheduler

**Status:** Accepted for v1; the superseded design is **Deferred** to v2
**Supersedes:** SDD v1.0 §6.3 (device enumeration with per-device exclusive slots, resource classes, and automatic CPU fallback) as v1 scope

### Context

SDD v1.0 specified a Resource Manager enumerating GPU devices, maintaining per-device exclusive slots, tagging job items with resource classes (`cpu`, `gpu-preferred`, `gpu-required`), and falling back to CPU under policy.

The target machine is a single-user Windows 11 desktop with one GPU. Per-device slot scheduling has nothing to schedule, and a resource-class taxonomy has one meaningful value.

### Decision

v1 selects an execution provider once at startup — CUDA, then DirectML, then CPU, overridable in Settings — and guards inference with a **single global `asyncio.Semaphore(1)`**, so at most one inference runs at a time regardless of device. CPU-bound preprocessing continues in threads (ADR-0005) alongside it.

CPU-only operation is not a separate fallback path: it is the same code with a different execution provider, and therefore exercised by default in CI where no GPU exists.

### Alternatives considered

- **The full resource manager (the superseded decision)** — retained as v2 design, triggered by a multi-GPU user or by batch throughput becoming the dominant complaint (TD-04). Rejected for v1 as substantial code to write and test for a machine configuration v1 does not target.
- **No concurrency limit at all** — rejected; concurrent inference on one GPU risks exhausting device memory, which fails in ways that are hard to diagnose.
- **A semaphore sized to a configured worker count** — rejected for v1 as a setting whose correct value the user cannot determine, and whose wrong value produces out-of-memory errors.

### Consequences

- Accepted: machines with multiple GPUs use one. Recorded as TD-04.
- Accepted: inference and preprocessing do not pipeline as aggressively as per-device slots would allow.
- Gained: two tasks removed; roughly ten lines replace a module requiring device-enumeration mocks to test.
- Gained: the same code path runs on GPU and CPU, so CPU-only correctness cannot silently rot.

---

## ADR-0010 — Windows path handling and platformdirs data layout

**Status:** Accepted (fills a gap; no prior decision existed)

### Context

Neither the PRD nor SDD v1.0 addressed filesystem realities the scanner meets on its first run against a real library: paths beyond `MAX_PATH`, case-insensitive comparison, UNC/network roots, symlinks and junctions, or where the application's own files belong on Windows. Left unspecified, each is decided ad hoc by whichever task hits it first — and long-path handling in particular fails by silently skipping files rather than raising.

### Decision

**Path handling.** Paths are `pathlib.Path` in code and UTF-8 text in the database: `library_root.path` absolute, `photo.relative_path` relative with `/` separators for portability. Additionally:

- Long-path support is enabled in the application manifest, and paths are `\\?\`-prefixed when opening files on Windows.
- A case-folded comparison key is stored alongside the original-case path; uniqueness on `(library_root_id, relative_path)` uses the folded key, so a library indexed on Windows behaves correctly if later opened on Linux.
- UNC and network roots are supported for reading; change detection on non-local roots defaults to size+mtime, with content hashing available on demand.
- Symlinks, junctions, and reparse points are **not** followed by default, preventing scan cycles and double-counting. Following them is an explicit per-root setting.
- Reserved names and trailing dots or spaces are tolerated on read and never generated on write.

**Data layout.** `platformdirs` provides correct locations on every OS with no Windows-specific code: the database, cache, models, and logs under the user's local-data directory; `config.toml` under the roaming-config directory; a `--portable` flag relocating all of it beside the executable. Only `config.toml` and the user-data tables are irreplaceable — everything else is derived and rebuildable.

### Alternatives considered

- **Storing absolute paths per photo** — rejected; moving or remounting a library root would invalidate every row. A root-relative path survives a drive-letter change.
- **Case-sensitive comparison everywhere** — rejected; produces duplicate rows for the same file on Windows.
- **Following symlinks by default** — rejected; a single self-referential junction turns a scan into an unbounded walk.
- **Hardcoding `%LOCALAPPDATA%`** — rejected; `platformdirs` costs one dependency and removes the only Windows-specific branch that would otherwise exist in path code.

### Consequences

- Accepted: one dependency (`platformdirs`).
- Accepted: the case-folded key adds a column and a small amount of write-path logic.
- Gained: long-path and network-path failures are designed for rather than discovered during a user's first scan of a real library.
- Gained: portability is preserved without platform branches, and the Linux/macOS path stays open at no v1 cost.

---

## ADR-0011 — Naive local capture time is authoritative

**Status:** Accepted (fills a gap; no prior decision existed)

### Context

EXIF `DateTimeOriginal` records local wall-clock time at the moment of capture, with **no timezone**. Most cameras never record an offset. SDD v1.0's `metadata.captured_at` column did not state whether the value is UTC, local, or naive.

This matters more than it appears. If naive local times are stored as if they were UTC, a photograph taken at 2 p.m. in Tokyo is filed at a different date for a user in London — and travel photography, precisely this product's subject, is where the error concentrates. The error is also expensive to correct after a large library has been indexed and searched.

### Decision

Three columns, with one designated authoritative:

| Column | Meaning |
|---|---|
| `captured_at_local` | Naive local wall-clock time exactly as recorded. **Authoritative** for all display and all date-range search. |
| `captured_at_offset_minutes` | Nullable. Populated only when a source genuinely supplies it (EXIF 2.31 `OffsetTimeOriginal`, GPS-derived time, or an XMP field). Never inferred. |
| `captured_at_utc` | Nullable. Computed only when an offset is known. |

Date-range queries and date display always use `captured_at_local`, so "photos from June 2024" matches the user's memory of the trip rather than a server's clock. Cross-timezone sorting uses `captured_at_utc` where available, falling back to local. Photos with no capture timestamp fall back to filesystem mtime, flagged `captured_at_source='mtime'` so the UI can distinguish a recorded time from a guess.

### Alternatives considered

- **Store UTC only, inferring the offset from the machine's current timezone** — rejected; the inference is wrong for every photograph not taken in the user's present timezone, and it is lossy — the original wall-clock value cannot be recovered.
- **Store naive local only** — nearly sufficient, and much of the value. Rejected because chronological ordering across timezones then has no correct answer even when the source *did* provide an offset.
- **Infer the offset from GPS coordinates for every photo** — rejected as a v1 default: it requires a timezone-boundary dataset and fails for photos without GPS. Available later as an explicit enrichment action.

### Consequences

- Accepted: three columns instead of one, and search code must consistently use `captured_at_local`. Enforced by keeping date filtering in one query-builder module.
- Accepted: cross-timezone chronological sorting is approximate when offsets are unknown — which is honest, because the information genuinely is not present in the file.
- Gained: date search results match user expectation, and the original recorded value is never destroyed. Retrofitting this after indexing a 200,000-photo library would mean re-reading every file.

---

## ADR-0012 — HEIC as an optional component; RAW via LibRaw

**Status:** Accepted (fills a gap; no prior decision existed)

### Context

iPhone libraries are substantially HEIC. HEIC decoding depends on HEVC, which carries patent-licensing considerations for redistributed binaries — a distribution constraint, not a technical one, and one that is far cheaper to plan for before an installer exists than to discover during packaging. RAW support spans many vendor formats and evolves with each camera release.

### Decision

- **RAW** decoding uses rawpy/LibRaw, bundled. Vendor coverage is a function of the bundled LibRaw version, which is pinned and recorded in the diagnostics bundle so an unsupported-format report is immediately actionable.
- **HEIC/HEIF** decoding uses `pillow-heif`, treated as an **optional component**. The application detects its availability at startup; when absent, HEIC files are indexed with their metadata (ExifTool reads them regardless) and shown with a placeholder thumbnail and a clear "HEIC support not installed" affordance, rather than being silently skipped or failing the scan.
- The licensing position for the chosen HEVC decoder distribution path is confirmed **before** the first installer is produced, not during packaging.

### Alternatives considered

- **Bundling HEIC support unconditionally** — simplest technically; deferred pending the licensing confirmation above. If confirmed acceptable, this ADR is amended and the optional component becomes standard.
- **Excluding HEIC entirely from v1** — rejected; it would make the application non-functional for a large share of modern libraries.
- **Converting HEIC to JPEG on import** — rejected outright; it writes to or alongside the user's originals for the application's own convenience, violating the read-only principle in ADR-0007.

### Consequences

- Accepted: HEIC availability may vary by installation, so capability status must be visible (SDD §16.4's degraded-mode surface covers this uniformly).
- Accepted: RAW coverage is bounded by the pinned LibRaw version; new camera bodies may need a dependency bump, which becomes routine maintenance.
- Gained: a licensing question that could have blocked release is resolved before the packaging phase rather than inside it.
- Gained: unsupported formats degrade visibly and per-file, instead of aborting a scan or vanishing from the index.
