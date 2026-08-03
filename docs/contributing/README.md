# Contributing

Read `AI_Development_Guide_v1.md` before making changes — it's the style
and architecture guide this codebase is held to (layering rules, no
premature abstraction, production-quality-only, etc.). The full design is
in `Local_AI_Photo_Intelligence_PRD_v2.md` (product requirements),
`Local_AI_Photo_Intelligence_SDD_v1.md` (system design — the section
numbers referenced throughout the codebase's comments and commit messages
point here), and `Architecture_Decision_Records_v1.md` (the "why" behind
decisions that read as unusual in isolation, e.g. why there's no actor/queue
for writes, why plugins are in-process only, why SQLite over a separate
vector DB).

`Local_AI_Photo_Intelligence_Implementation_Plan_v1.md`'s **Section 12
(MVP Scope Overlay)** is the authoritative scope of record for v1 — where
it disagrees with the SDD's earlier sections, the overlay wins. Check it
before picking up any `TASK-NNN`: many tasks are revised or deferred
relative to their original description.

## Bootstrap

See the root `README.md` — it covers the Python/Node/ExifTool prerequisites,
`pip install -e ".[dev]"`, HEIC's optional extra, and how the CLIP/caption
providers' model cache works.

## Repository layout

- `src/core/` — the Python core service (FastAPI + `pywebview` shell,
  one process per ADR-0002).
- `src/ui/` — the React/TypeScript frontend.
- `alembic/` — schema migrations (`alembic upgrade head` / `downgrade base`).
- `tests/unit/`, `tests/integration/` — mirrors `src/core/`'s structure;
  integration tests use real SQLite/FTS5/`sqlite-vec`, real (tiny) ONNX
  models where available, no mocked infra.
- `tools/` — one-off developer tooling (`synth_library.py`, the synthetic
  library generator used for the ~100k-photo scale check).
- `packaging/pyinstaller/`, `packaging/inno/` — the frozen-build spec and
  Windows installer script (TASK-097/098).
- `.github/workflows/` — CI: `ci-core.yml` (Python lint/type/test),
  `ci-ui.yml` (UI lint/type/test), `package-windows.yml` (frozen build +
  installer, triggered manually or on a `v*` tag — not run on every PR,
  since a full freeze build is too slow/heavy for that).

## Validation before every commit

Backend:

```bash
ruff check src tests alembic tools
ruff format --check src tests alembic tools
mypy --strict src/core tools
lint-imports
pytest
```

Frontend (from `src/ui/`):

```bash
npm run lint
npm run typecheck
npm run format:check
npm run test -- --run
```

`pre-commit install` wires the backend checks in as a local git hook. Every
PR should pass all of the above — the Implementation Plan's **Section 7
(Definition of Done)** is the full per-task checklist this maps to; `TASK-101`
sweeps it once per release rather than per-task (see
`../RELEASE_CHECKLIST.md`).

## A note on the layering rule

`ci-core.yml` runs `lint-imports`, enforcing one contract: **api →
application/infrastructure → domain**. `core/domain/` must never import
from `core/infrastructure/` or `core/api/`. This is what keeps e.g.
`core/domain/providers.py`'s `Protocol`s swappable without dragging
ONNX Runtime into code that has no business importing it.
