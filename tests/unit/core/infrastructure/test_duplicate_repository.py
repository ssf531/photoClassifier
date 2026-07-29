import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.infrastructure.db.base import Base
from core.infrastructure.db.duplicate_models import DuplicateGroup, DuplicateGroupMember
from core.infrastructure.db.engine import create_engine, create_session_factory
from core.infrastructure.db.library_models import LibraryRoot, Photo
from core.infrastructure.db.write_connection import WriteConnection
from core.infrastructure.duplicate_repository import (
    DuplicateGroupMemberRepository,
    DuplicateGroupRepository,
)
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository


@pytest.fixture
async def env(
    tmp_path: Path,
) -> AsyncIterator[
    tuple[
        DuplicateGroupRepository,
        DuplicateGroupMemberRepository,
        PhotoRepository,
        LibraryRootRepository,
    ]
]:
    engine = create_engine(tmp_path / "duplicates.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)
    try:
        yield (
            DuplicateGroupRepository(sessions, writer),
            DuplicateGroupMemberRepository(sessions, writer),
            PhotoRepository(sessions, writer),
            LibraryRootRepository(sessions, writer),
        )
    finally:
        await writer.close()
        await engine.dispose()


async def _make_photo(photo_repo: PhotoRepository, library_root_id: uuid.UUID) -> Photo:
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    return await photo_repo.create(
        Photo(
            library_root_id=library_root_id,
            relative_path=f"{uuid.uuid4()}.jpg",
            relative_path_folded=f"{uuid.uuid4()}.jpg",
            size_bytes=1,
            file_mtime=now,
            status="active",
        )
    )


async def test_create_group_and_add_members(
    env: tuple[
        DuplicateGroupRepository,
        DuplicateGroupMemberRepository,
        PhotoRepository,
        LibraryRootRepository,
    ],
) -> None:
    group_repo, member_repo, photo_repo, library_root_repo = env
    root = await library_root_repo.create(LibraryRoot(path="/library"))
    keeper = await _make_photo(photo_repo, root.id)
    other = await _make_photo(photo_repo, root.id)

    group = await group_repo.create(DuplicateGroup(detection_method="dhash@1"))
    await member_repo.create(
        DuplicateGroupMember(
            group_id=group.id, photo_id=keeper.id, similarity_score=1.0, is_recommended_keeper=True
        )
    )
    await member_repo.create(
        DuplicateGroupMember(
            group_id=group.id,
            photo_id=other.id,
            similarity_score=0.9,
            is_recommended_keeper=False,
        )
    )

    members = await member_repo.list_by_group(group.id)
    assert {m.photo_id for m in members} == {keeper.id, other.id}
    keeper_row = next(m for m in members if m.photo_id == keeper.id)
    assert keeper_row.is_recommended_keeper is True
