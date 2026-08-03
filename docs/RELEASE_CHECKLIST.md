# v1 Release-Candidate Checklist (TASK-101)

Sweeps the Implementation Plan's **Section 7 (Definition of Done)** at a
whole-repository level, plus Phase 10 / EPIC-24's acceptance criteria.
Evidence dates and commit hashes below are from this checklist's own
authoring session; re-verify before actually cutting a release rather than
trusting this snapshot indefinitely.

**Status: NOT yet release-ready.** TASK-101 formally depends on TASK-100
(security review pass), which has not been done. Two concrete findings
below were noticed while assembling this checklist and should feed
directly into TASK-100 rather than being treated as already resolved.

## Section 7 — Definition of Done (aggregate, whole-repo)

- [x] **Build succeeds** — backend: `pip install -e ".[dev]"` on a fresh
      Python 3.12 venv succeeds. Frontend: `npm run build` (`src/ui/`)
      succeeds. Frozen build: `pyinstaller packaging/pyinstaller/core.spec`
      succeeds and the result runs standalone (TASK-097).
- [x] **Tests pass** — backend: 469 passed (`pytest`, Python 3.12 venv).
      Frontend: 58 passed across 15 files (`npm run test -- --run`).
- [x] **No compiler/type-checker warnings** — `mypy --strict src/core tools`:
      0 errors across 90 files. `tsc --noEmit` (`src/ui/`): 0 errors.
      `eslint .` (`src/ui/`): 0 errors, 2 pre-existing warnings (React
      Compiler memoization notes on `ProgressSocketContext.tsx` and
      `PhotoGrid.tsx` — informational, not defects).
- [ ] **No TODOs, no placeholder logic** — not re-audited as part of this
      pass; each task's own commit history is the evidence trail. A full
      `TODO`/`FIXME`/`NotImplementedError` grep sweep across the tree is
      cheap and worth doing once as part of TASK-100, not duplicated here.
- [x] **No dead/fake architecture** — `lint-imports` (the layering
      contract: api → application/infrastructure → domain) passes with 0
      broken contracts across 236 dependencies.
- [ ] **Code reviewed** — no human review has occurred in this repo's
      history; every commit this session was authored and validated by an
      AI agent working from the Implementation Plan. This item cannot be
      checked off without an actual human (or designated review-agent)
      pass before release.
- [x] **Documentation updated** — `docs/user/`, `docs/plugin-authoring/`,
      `docs/contributing/` added this task; root `README.md` was already
      current for bootstrap/run/config.
- [x] **Traceability preserved** — commit messages across this project
      consistently reference their `TASK-NNN` ID and relevant SDD section.
- [ ] **Performance acceptable** — TASK-0E (real-library ~100k-photo scale
      check) has not been run. No obvious unbounded query is currently
      known (TASK-096 audited and fixed the two that existed), but the
      scale check itself is still outstanding.
- [ ] **Safety-critical tasks** — v1 has no code path reaching
      move/delete on an original file (TASK-078, the two-stage-confirm
      executor, is deferred to v2 — ADR-0007), so there's no `execute()`
      invariant to test yet. However, the SDD (§13.2) claims *"CI enforces
      [read-only originals] with a targeted check"* — **no such check
      currently exists** in `.github/workflows/` or `tests/`. This is a
      real gap between the SDD's claim and the repo's actual state; it
      should be either added (a static check that no `src/core` module
      calls `os.remove`/`os.rename`/`shutil.move`/`Path.unlink` on a
      library-root-relative path) or the SDD's claim corrected, as part
      of TASK-100.
- [x] **Secrets hygiene** — no credentials/tokens/API keys are committed.
      SDD §13.4's OS-keychain requirement is for connector credentials;
      v1 ships no connectors (all deferred to v1.1/v2 per §12), so this
      item is not yet applicable rather than passing by omission.

## Phase 10 / EPIC-24 acceptance criteria

- [x] **FEAT-095 (frozen build)**: a frozen build runs the full core
      service with no Python interpreter or source checkout present
      (verified TASK-097: ran `core.exe --no-window` from a directory
      outside the repo, confirmed migrations, `/health`, and
      `/api/v1/plugins` all work).
- [~] **FEAT-096 (installer)**: install → run → uninstall validated
      end-to-end (TASK-098) with one caveat found during that validation:
      **ExifTool is not bundled into the frozen build or the installer** —
      `find_exiftool()` (`core/infrastructure/exiftool_process.py`) only
      checks `PATH`, and neither `packaging/pyinstaller/core.spec` nor
      `packaging/inno/core.iss` bundles the `exiftool.exe` binary. The app
      itself degrades gracefully (metadata reads are skipped rather than
      crashing when ExifTool is absent), but EPIC-24's acceptance
      criterion — *"a clean-machine install (no dev tools present) ...
      completes a scan + AI pass + search query end-to-end using only the
      packaged installer"* — will not fully hold on a machine without
      ExifTool already on `PATH`, since metadata extraction (camera model,
      capture date, etc.) is part of a normal scan. This should be fixed
      (bundle the binary and point `find_exiftool()` at the bundled copy
      first, falling back to `PATH`) before shipping, tracked as follow-up
      to TASK-097/098.
- [ ] **Milestone 8 (Production Ready)**: blocked on TASK-100 and TASK-0E
      above, plus the ExifTool bundling gap.

## Outstanding before sign-off

1. TASK-100 — security review pass (SDD §13 sweep; the two findings above
   are a running start on it, not a substitute for the full pass).
2. TASK-0E — real-library ~100k-photo scale check.
3. Bundle ExifTool into the frozen build/installer, or explicitly document
   it as an install prerequisite if bundling is deferred.
4. A human (or designated review-agent) code-review pass — "Code
   reviewed" cannot be self-certified.
