from core.domain.duplicates import DuplicateGroupMemberSummary, DuplicateGroupSummary
from core.infrastructure.duplicate_repository import (
    DuplicateGroupMemberRepository,
    DuplicateGroupRepository,
)


class DuplicateReviewService:
    """Assembles `duplicate_group` rows with their members for the Duplicate
    Review UI (TASK-076): `is_recommended_keeper` (computed upstream by
    TASK-046's detector) is surfaced as a suggestion only -- nothing here
    selects a keeper or removes a photo.
    """

    def __init__(
        self, group_repo: DuplicateGroupRepository, member_repo: DuplicateGroupMemberRepository
    ) -> None:
        self._groups = group_repo
        self._members = member_repo

    async def list_groups(self, *, limit: int, offset: int) -> list[DuplicateGroupSummary]:
        groups = await self._groups.list(limit=limit, offset=offset)
        summaries = []
        for group in groups:
            members = await self._members.list_by_group(group.id)
            summaries.append(
                DuplicateGroupSummary(
                    id=group.id,
                    detection_method=group.detection_method,
                    created_at=group.created_at,
                    members=[
                        DuplicateGroupMemberSummary(
                            photo_id=member.photo_id,
                            similarity_score=member.similarity_score,
                            is_recommended_keeper=member.is_recommended_keeper,
                        )
                        for member in members
                    ],
                )
            )
        return summaries
