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
from core.infrastructure.duplicate_review_service import DuplicateReviewService
from core.infrastructure.library_repository import LibraryRootRepository, PhotoRepository


class _Env:
    def __init__(
        self,
        service: DuplicateReviewService,
        photo_repo: PhotoRepository,
        group_repo: DuplicateGroupRepository,
        member_repo: DuplicateGroupMemberRepository,
        library_root_id: uuid.UUID,
    ) -> None:
        self.service = service
        self.photo_repo = photo_repo
        self.group_repo = group_repo
        self.member_repo = member_repo
        self.library_root_id = library_root_id

    async def make_photo(self) -> uuid.UUID:
        now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
        name = f"{uuid.uuid4()}.jpg"
        photo = await self.photo_repo.create(
            Photo(
                library_root_id=self.library_root_id,
                relative_path=name,
                relative_path_folded=name.lower(),
                size_bytes=1,
                file_mtime=now,
                status="active",
            )
        )
        return photo.id


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "duplicate_review.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    library_root_repo = LibraryRootRepository(sessions, writer)
    root = await library_root_repo.create(LibraryRoot(path="/library"))
    photo_repo = PhotoRepository(sessions, writer)
    group_repo = DuplicateGroupRepository(sessions, writer)
    member_repo = DuplicateGroupMemberRepository(sessions, writer)
    service = DuplicateReviewService(group_repo, member_repo)

    try:
        yield _Env(service, photo_repo, group_repo, member_repo, root.id)
    finally:
        await writer.close()
        await engine.dispose()


async def test_list_groups_returns_no_groups_when_none_exist(env: _Env) -> None:
    assert await env.service.list_groups(limit=10, offset=0) == []


async def test_list_groups_nests_members_with_keeper_flag(env: _Env) -> None:
    keeper = await env.make_photo()
    other = await env.make_photo()
    group = await env.group_repo.create(DuplicateGroup(detection_method="dhash@1"))
    await env.member_repo.create(
        DuplicateGroupMember(
            group_id=group.id, photo_id=keeper, similarity_score=1.0, is_recommended_keeper=True
        )
    )
    await env.member_repo.create(
        DuplicateGroupMember(
            group_id=group.id, photo_id=other, similarity_score=0.9, is_recommended_keeper=False
        )
    )

    groups = await env.service.list_groups(limit=10, offset=0)

    assert len(groups) == 1
    assert groups[0].detection_method == "dhash@1"
    by_photo = {m.photo_id: m for m in groups[0].members}
    assert by_photo[keeper].is_recommended_keeper is True
    assert by_photo[other].is_recommended_keeper is False
    assert by_photo[other].similarity_score == 0.9


async def test_list_groups_paginates_across_groups(env: _Env) -> None:
    for _ in range(3):
        photo_id = await env.make_photo()
        group = await env.group_repo.create(DuplicateGroup(detection_method="dhash@1"))
        await env.member_repo.create(
            DuplicateGroupMember(
                group_id=group.id,
                photo_id=photo_id,
                similarity_score=1.0,
                is_recommended_keeper=True,
            )
        )

    first_page = await env.service.list_groups(limit=2, offset=0)
    second_page = await env.service.list_groups(limit=2, offset=2)

    assert len(first_page) == 2
    assert len(second_page) == 1
