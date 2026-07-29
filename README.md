# Photo Intelligence

Local AI photo library manager. One Python core service (FastAPI, displayed in a
`pywebview` window) plus a React/TypeScript UI, backed by a single SQLite file.

See `Local_AI_Photo_Intelligence_PRD_v2.md`, `Local_AI_Photo_Intelligence_SDD_v1.md`,
`Architecture_Decision_Records_v1.md`, and `AI_Development_Guide_v1.md` for the full
design. Read the AI Development Guide before making changes.

## Bootstrap

Requires Python 3.12+, Node.js 20+, and [ExifTool](https://exiftool.org/) on `PATH`.
Metadata reads shell out to one persistent `exiftool -stay_open` process (see
`core/infrastructure/exiftool_process.py`); the packaged installer will bundle
the binary rather than relying on `PATH`.

```bash
pip install -e ".[dev]"
cd src/ui && npm install
```

Raster (JPEG/PNG/TIFF/WebP) thumbnails use Pillow; RAW (CR2/CR3/NEF/ARW/DNG/RAF/ORF/RW2)
uses `rawpy`/LibRaw, bundled per ADR-0012. HEIC/HEIF is optional (ADR-0012): install
`pip install -e ".[heic]"` for it, or leave it out — the app detects its absence at
startup and shows a placeholder instead of failing (see `core/infrastructure/heic_support.py`).

## Run

```bash
python -m core
```

Prints the bound port (fixed at `127.0.0.1:8756`) and the per-launch bearer token
to the console (never written to disk). `GET /health` and `GET /version` both
require `Authorization: Bearer <token>`. Opens a desktop window on the served
UI; pass `--no-window` to run the API server only (used by automated tests).

## Configuration

Settings resolve in layers: built-in default < `config.toml` < environment
variable (`PHOTO_INTELLIGENCE_<KEY>`) < explicit override. `config.toml` lives
under the OS-standard config directory (via `platformdirs`) unless
`PHOTO_INTELLIGENCE_PORTABLE=1` is set, in which case all app data (config,
cache, database, logs) resolves to a `data/` folder beside the executable.
See `src/core/config.toml.example` for the available keys.

## Database

One SQLite file (`photo-intelligence.db`, under the resolved data directory —
see Configuration above), WAL mode, with the `sqlite-vec` extension loaded on
every connection. Schema changes are Alembic migrations:

```bash
alembic upgrade head
alembic downgrade base
```

Point migrations at an arbitrary file (e.g. for tests) with
`alembic -x db_path=/path/to/file.db upgrade head`.

## Development checks

```bash
ruff check src tests alembic
ruff format --check src tests alembic
mypy --strict src/core
lint-imports
pytest
```

`pre-commit install` wires these (plus the UI equivalents) in as a local git hook.
