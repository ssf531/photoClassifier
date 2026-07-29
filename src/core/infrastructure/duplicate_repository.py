import uuid

from sqlalchemy import select

from core.infrastructure.db.duplicate_models import DuplicateGroup, DuplicateGroupMember
from core.infrastructure.db.repository import SqlAlchemyRepository


class DuplicateGroupRepository(SqlAlchemyRepository[DuplicateGroup]):
    model = DuplicateGroup


class DuplicateGroupMemberRepository(SqlAlchemyRepository[DuplicateGroupMember]):
    model = DuplicateGroupMember

    async def list_by_group(self, group_id: uuid.UUID) -> list[DuplicateGroupMember]:
        async with self._read_sessions() as session:
            result = await session.execute(
                select(DuplicateGroupMember)
                .where(DuplicateGroupMember.group_id == group_id)
                .order_by(DuplicateGroupMember.id)
            )
            return list(result.scalars().all())
