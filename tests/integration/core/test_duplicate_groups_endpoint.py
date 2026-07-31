from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.api.app import create_app
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

TOKEN = "known-token"


class _Env:
    def __init__(self, client: TestClient, keeper_id: str, other_id: str) -> None:
        self.client = client
        self.keeper_id = keeper_id
        self.other_id = other_id


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[_Env]:
    engine = create_engine(tmp_path / "duplicate_groups.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    writer = WriteConnection(engine)
    sessions = create_session_factory(engine)

    library_root_repo = LibraryRootRepository(sessions, writer)
    photo_repo = PhotoRepository(sessions, writer)
    group_repo = DuplicateGroupRepository(sessions, writer)
    member_repo = DuplicateGroupMemberRepository(sessions, writer)
    root = await library_root_repo.create(LibraryRoot(path="/library"))
    now = datetime.now(timezone.utc)  # noqa: UP017 -- kept pre-3.11 alias pending broader migration
    keeper = await photo_repo.create(
        Photo(
            library_root_id=root.id,
            relative_path="a.jpg",
            relative_path_folded="a.jpg",
            size_bytes=1,
            file_mtime=now,
            status="active",
        )
    )
    other = await photo_repo.create(
        Photo(
            library_root_id=root.id,
            relative_path="b.jpg",
            relative_path_folded="b.jpg",
            size_bytes=1,
            file_mtime=now,
            status="active",
        )
    )
    group = await group_repo.create(DuplicateGroup(detection_method="dhash@1"))
    await member_repo.create(
        DuplicateGroupMember(
            group_id=group.id, photo_id=keeper.id, similarity_score=1.0, is_recommended_keeper=True
        )
    )
    await member_repo.create(
        DuplicateGroupMember(
            group_id=group.id, photo_id=other.id, similarity_score=0.9, is_recommended_keeper=False
        )
    )

    service = DuplicateReviewService(group_repo, member_repo)
    app = create_app(token=TOKEN, duplicate_review_service=service)
    client = TestClient(app)

    try:
        yield _Env(client, str(keeper.id), str(other.id))
    finally:
        await writer.close()
        await engine.dispose()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_list_duplicate_groups_requires_auth(env: _Env) -> None:
    response = env.client.get("/api/v1/duplicate-groups")

    assert response.status_code == 401


def test_list_duplicate_groups_returns_members_with_keeper_flag(env: _Env) -> None:
    response = env.client.get("/api/v1/duplicate-groups", headers=_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    members = {m["photo_id"]: m for m in body["items"][0]["members"]}
    assert members[env.keeper_id]["is_recommended_keeper"] is True
    assert members[env.other_id]["is_recommended_keeper"] is False
    assert body["next_offset"] is None


def test_list_duplicate_groups_returns_503_when_not_configured() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.get("/api/v1/duplicate-groups", headers=_auth_headers())

    assert response.status_code == 503
