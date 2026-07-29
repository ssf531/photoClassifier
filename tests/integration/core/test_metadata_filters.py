import asyncio
from argparse import Namespace
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from core.domain.search import DateRange, GpsBoundingBox, MetadataFilters
from core.infrastructure.collection_repository import UserDataRepository
from core.infrastructure.db.collection_models import UserData
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.metadata_models import Metadata
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository
from core.infrastructure.metadata_filters import filter_photo_ids
from core.infrastructure.metadata_repository import MetadataRepository

REPO_ROOT = Path(__file__).resolve().parents[3]


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.cmd_opts = Namespace(x=[f"db_path={db_path}"])
    return cfg


class _Env:
    def __init__(self, sessions: object, photos: dict[str, Photo]) -> None:
        self.sessions = sessions
        self.photos = photos


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    db_path = tmp_path / "metadata_filters.db"
    await asyncio.to_thread(command.upgrade, _alembic_config(db_path), "head")

    engine = create_engine(db_path)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    photo_repo = PhotoRepository(sessions, writer)
    library_root_repo = LibraryRootRepository(sessions, writer)
    metadata_repo = MetadataRepository(sessions, writer)
    user_data_repo = UserDataRepository(sessions, writer)
    root = await library_root_repo.create(LibraryRoot(path="/library"))

    now = datetime(2026, 6, 15, 12, 0, 0)  # naive local time, matching captured_at_local

    async def make_photo(
        name: str,
        *,
        captured_at_local: datetime | None,
        camera_model: str | None,
        rating: int | None,
        gps: tuple[float, float] | None,
    ) -> Photo:
        photo = await photo_repo.create(
            Photo(
                library_root_id=root.id,
                relative_path=name,
                relative_path_folded=name.lower(),
                size_bytes=1,
                file_mtime=datetime.now(timezone.utc),  # noqa: UP017
                status="active",
                captured_at_local=captured_at_local,
            )
        )
        if camera_model is not None or gps is not None:
            await metadata_repo.upsert(
                Metadata(
                    photo_id=photo.id,
                    camera_model=camera_model,
                    gps_lat=gps[0] if gps else None,
                    gps_lon=gps[1] if gps else None,
                    raw_exif_blob={},
                )
            )
        if rating is not None:
            await user_data_repo.upsert(UserData(photo_id=photo.id, rating=rating, favourite=False))
        return photo

    photos = {
        "new_york": await make_photo(
            "new_york.jpg",
            captured_at_local=now,
            camera_model="Canon EOS R5",
            rating=5,
            gps=(40.7128, -74.0060),
        ),
        "paris": await make_photo(
            "paris.jpg",
            captured_at_local=now - timedelta(days=200),
            camera_model="Nikon Z6",
            rating=2,
            gps=(48.8566, 2.3522),
        ),
        "no_metadata": await make_photo(
            "no_metadata.jpg",
            captured_at_local=None,
            camera_model=None,
            rating=None,
            gps=None,
        ),
    }

    try:
        yield _Env(sessions, photos)
    finally:
        await writer.close()
        await engine.dispose()


async def test_no_filters_returns_all_photos(env: _Env) -> None:
    ids = await filter_photo_ids(env.sessions, MetadataFilters(), limit=10, offset=0)
    assert set(ids) == {p.id for p in env.photos.values()}


async def test_date_range_filter(env: _Env) -> None:
    filters = MetadataFilters(
        date_range=DateRange(start=datetime(2026, 1, 1), end=datetime(2026, 12, 31))
    )
    ids = await filter_photo_ids(env.sessions, filters, limit=10, offset=0)
    assert ids == [env.photos["new_york"].id]


async def test_camera_model_filter(env: _Env) -> None:
    filters = MetadataFilters(camera_model="Nikon Z6")
    ids = await filter_photo_ids(env.sessions, filters, limit=10, offset=0)
    assert ids == [env.photos["paris"].id]


async def test_min_rating_filter(env: _Env) -> None:
    filters = MetadataFilters(min_rating=3)
    ids = await filter_photo_ids(env.sessions, filters, limit=10, offset=0)
    assert ids == [env.photos["new_york"].id]


async def test_gps_bounding_box_filter(env: _Env) -> None:
    # A box around New York only.
    filters = MetadataFilters(
        gps_bbox=GpsBoundingBox(min_lat=40.0, max_lat=41.0, min_lon=-75.0, max_lon=-73.0)
    )
    ids = await filter_photo_ids(env.sessions, filters, limit=10, offset=0)
    assert ids == [env.photos["new_york"].id]


async def test_combined_filters_are_intersected(env: _Env) -> None:
    filters = MetadataFilters(
        date_range=DateRange(start=datetime(2025, 1, 1)),
        camera_model="Canon EOS R5",
        min_rating=1,
        gps_bbox=GpsBoundingBox(min_lat=30.0, max_lat=50.0, min_lon=-80.0, max_lon=-70.0),
    )
    ids = await filter_photo_ids(env.sessions, filters, limit=10, offset=0)
    assert ids == [env.photos["new_york"].id]


async def test_combined_filters_with_no_matches_returns_empty(env: _Env) -> None:
    # Canon body, but Paris coordinates -- no photo satisfies both.
    filters = MetadataFilters(
        camera_model="Canon EOS R5",
        gps_bbox=GpsBoundingBox(min_lat=48.0, max_lat=49.0, min_lon=2.0, max_lon=3.0),
    )
    ids = await filter_photo_ids(env.sessions, filters, limit=10, offset=0)
    assert ids == []
