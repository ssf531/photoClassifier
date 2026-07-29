import sqlite3
from argparse import Namespace
from pathlib import Path

from alembic.config import Config

from alembic import command

REPO_ROOT = Path(__file__).resolve().parents[3]


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.cmd_opts = Namespace(x=[f"db_path={db_path}"])
    return cfg


def _alembic_version_rows(db_path: Path) -> list[tuple[str]]:
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT version_num FROM alembic_version").fetchall()


def _table_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {row[0] for row in rows}


def test_alembic_upgrade_head_then_downgrade_base_round_trips(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    cfg = _alembic_config(db_path)

    command.upgrade(cfg, "head")
    assert db_path.is_file()
    assert len(_alembic_version_rows(db_path)) == 1
    assert {"job", "job_item", "library_root", "photo"} <= _table_names(db_path)

    command.downgrade(cfg, "base")
    assert _alembic_version_rows(db_path) == []
    assert _table_names(db_path).isdisjoint({"job", "job_item", "library_root", "photo"})
