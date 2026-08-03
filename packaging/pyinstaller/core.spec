# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for the frozen core service (SDD §3.14, TASK-097).

Bundles the Python core, the built React static assets, and every non-.py
data file the app reads at runtime (alembic migrations, plugin manifests,
the tag vocabulary) into one executable tree. Heavy ML dependencies
(onnxruntime, tokenizers, rawpy) are imported lazily by the application
code itself, not excluded here -- PyInstaller's own analysis still needs
to see and bundle them for whenever a provider first uses them.

Run from the repo root:
    pyinstaller packaging/pyinstaller/core.spec --distpath dist --workpath build
"""

import glob
import os

import sqlite_vec

REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))  # noqa: F821 -- injected by PyInstaller
SRC_DIR = os.path.join(REPO_ROOT, "src")
ENTRY_SCRIPT = os.path.join(SRC_DIR, "core", "__main__.py")

datas = [
    (os.path.join(REPO_ROOT, "alembic.ini"), "."),
    (os.path.join(REPO_ROOT, "alembic", "env.py"), "alembic"),
    (os.path.join(REPO_ROOT, "alembic", "script.py.mako"), "alembic"),
]
for migration in glob.glob(os.path.join(REPO_ROOT, "alembic", "versions", "*.py")):
    datas.append((migration, os.path.join("alembic", "versions")))

for manifest in glob.glob(os.path.join(SRC_DIR, "core", "plugins", "*", "plugin.toml")):
    plugin_name = os.path.basename(os.path.dirname(manifest))
    datas.append((manifest, os.path.join("src", "core", "plugins", plugin_name)))

datas.append(
    (os.path.join(SRC_DIR, "core", "tag_vocabulary_v1.json"), os.path.join("src", "core"))
)

# sqlite_vec's native extension is loaded via SQLite's own load_extension()
# at runtime (ADR-0003), never through Python import machinery -- PyInstaller's
# static analysis has no way to see it, so it must be bundled explicitly.
# `.dll` only: packaging is Windows-only in v1 (SDD §3.14/§12).
datas.append((sqlite_vec.loadable_path() + ".dll", "sqlite_vec"))

UI_DIST_DIR = os.path.join(SRC_DIR, "ui", "dist")
if not os.path.isdir(UI_DIST_DIR):
    raise SystemExit(
        f"{UI_DIST_DIR} does not exist -- run `npm run build` in src/ui before freezing."
    )

a = Analysis(  # noqa: F821 -- injected by PyInstaller
    [ENTRY_SCRIPT],
    pathex=[SRC_DIR],
    binaries=[],
    datas=datas,
    # SQLAlchemy resolves the "sqlite+aiosqlite" dialect string to this
    # module by dynamic entry-point lookup (sqlalchemy.dialects.registry),
    # never a static `import aiosqlite` PyInstaller's analysis can see.
    hiddenimports=["aiosqlite"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
a.datas += Tree(UI_DIST_DIR, prefix=os.path.join("src", "ui", "dist"))  # noqa: F821

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="core",
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="core",
)
