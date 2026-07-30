"""Synthetic library generator (TASK-036/SDD Section 14).

Generates N synthetic `photo`/`metadata` rows with randomized-but-realistic
EXIF and content hashes, for exercising the Browse UI and the 100k-scale
check (TASK-065) without needing a real photo corpus. No image files are
written to disk -- "minimal valid JPEG bytes" are hashed in memory per row
to produce a realistic-looking, correctly-formatted content hash without
the I/O cost of 100k real files.

Usage:
    python tools/synth_library.py --count 100000 --out <db path>
"""

import argparse
import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import xxhash
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.metadata_models import Metadata
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository

REPO_ROOT = Path(__file__).resolve().parents[1]
_BATCH_SIZE = 2000

_CAMERA_MAKES_MODELS = [
    ("Canon", "EOS R5"),
    ("Nikon", "Z6 II"),
    ("Sony", "A7 IV"),
    ("Fujifilm", "X-T5"),
    ("Apple", "iPhone 14 Pro"),
]
_LENSES = ["24-70mm f/2.8", "50mm f/1.8", "70-200mm f/2.8", "16-35mm f/4"]
_FOCAL_LENGTHS = [24.0, 35.0, 50.0, 85.0, 105.0, 200.0]
_ISO_VALUES = [100, 200, 400, 800, 1600, 3200]
_RESOLUTIONS = [(4000, 3000), (6000, 4000), (8000, 6000)]


def _minimal_jpeg_bytes(index: int) -> bytes:
    return b"\xff\xd8\xff\xe0" + index.to_bytes(8, "big") + b"\xff\xd9"


def _content_hash(index: int) -> str:
    return xxhash.xxh3_64(_minimal_jpeg_bytes(index)).hexdigest()


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.cmd_opts = argparse.Namespace(x=[f"db_path={db_path}"])
    return cfg


def _random_row(
    rng: random.Random, index: int, library_root_id: uuid.UUID, base_time: datetime
) -> tuple[Photo, Metadata]:
    photo_id = uuid.uuid4()
    captured_at = base_time - timedelta(minutes=rng.randint(0, 5_000_000))
    photo = Photo(
        id=photo_id,
        library_root_id=library_root_id,
        relative_path=f"synthetic/{index:07d}.jpg",
        relative_path_folded=f"synthetic/{index:07d}.jpg",
        content_hash=_content_hash(index),
        size_bytes=rng.randint(500_000, 25_000_000),
        file_mtime=captured_at,
        status="active",
        captured_at_local=captured_at.replace(tzinfo=None),
        captured_at_offset_minutes=0,
        captured_at_utc=captured_at,
        captured_at_source="exif",
    )
    make, model = rng.choice(_CAMERA_MAKES_MODELS)
    width, height = rng.choice(_RESOLUTIONS)
    metadata = Metadata(
        photo_id=photo_id,
        camera_make=make,
        camera_model=model,
        lens=rng.choice(_LENSES),
        focal_length=rng.choice(_FOCAL_LENGTHS),
        aperture=round(rng.uniform(1.4, 11.0), 1),
        shutter_speed=round(rng.uniform(1 / 4000, 1.0), 5),
        iso=rng.choice(_ISO_VALUES),
        gps_lat=round(rng.uniform(-90, 90), 6),
        gps_lon=round(rng.uniform(-180, 180), 6),
        width=width,
        height=height,
        orientation=1,
        raw_exif_blob={},
    )
    return photo, metadata


async def generate(db_path: Path, count: int, *, seed: int = 0) -> None:
    await asyncio.to_thread(command.upgrade, _alembic_config(db_path), "head")

    engine = create_engine(db_path)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)
    library_root_repo = LibraryRootRepository(sessions, writer)

    root = await library_root_repo.create(
        LibraryRoot(path=str(db_path.parent / "synthetic-library"))
    )

    rng = random.Random(seed)
    base_time = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration

    generated = 0
    try:
        while generated < count:
            batch_end = min(generated + _BATCH_SIZE, count)
            async with writer.transaction() as connection:
                session = AsyncSession(bind=connection, expire_on_commit=False)
                for index in range(generated, batch_end):
                    photo, metadata = _random_row(rng, index, root.id, base_time)
                    session.add(photo)
                    session.add(metadata)
                await session.flush()
            generated = batch_end
    finally:
        await writer.close()
        await engine.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="synth-library")
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    asyncio.run(generate(args.out, args.count, seed=args.seed))


if __name__ == "__main__":
    main()
