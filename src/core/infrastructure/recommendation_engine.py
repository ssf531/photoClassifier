import uuid

from core.domain.plugins import Capability
from core.domain.recommendations import Recommendation, RecommendationCategory
from core.infrastructure.ai_result_repository import AiResultRepository
from core.infrastructure.duplicate_repository import DuplicateGroupMemberRepository

_PAGE_SIZE = 500
_SCREENSHOT_TAG_LABEL = "screenshot"


class RecommendationEngine:
    """Groups existing AI results into actionable suggestion sets (SDD
    §10.2: "these N photos look like screenshots," "these N are
    near-identical"). Read-only: it never writes a collection or touches a
    photo's file -- turning a suggestion into a collection is TASK-076's
    job, via the existing CollectionManager.add_members().
    """

    def __init__(
        self,
        ai_result_repo: AiResultRepository,
        duplicate_member_repo: DuplicateGroupMemberRepository,
    ) -> None:
        self._ai_results = ai_result_repo
        self._duplicate_members = duplicate_member_repo

    async def list_recommendations(self) -> list[Recommendation]:
        return [
            Recommendation(
                category=RecommendationCategory.SCREENSHOTS, photo_ids=await self._screenshots()
            ),
            Recommendation(
                category=RecommendationCategory.LOW_QUALITY, photo_ids=await self._low_quality()
            ),
            Recommendation(
                category=RecommendationCategory.NEAR_DUPLICATES,
                photo_ids=await self._near_duplicates(),
            ),
        ]

    async def _screenshots(self) -> list[uuid.UUID]:
        photo_ids: list[uuid.UUID] = []
        offset = 0
        while True:
            page = await self._ai_results.list_current_by_capability(
                Capability.TAG.value, limit=_PAGE_SIZE, offset=offset
            )
            for result in page:
                tags = result.payload.get("tags", [])
                if any(tag.get("label") == _SCREENSHOT_TAG_LABEL for tag in tags):
                    photo_ids.append(result.photo_id)
            if len(page) < _PAGE_SIZE:
                return photo_ids
            offset += _PAGE_SIZE

    async def _low_quality(self) -> list[uuid.UUID]:
        photo_ids: list[uuid.UUID] = []
        offset = 0
        while True:
            page = await self._ai_results.list_current_by_capability(
                Capability.QUALITY.value, limit=_PAGE_SIZE, offset=offset
            )
            for result in page:
                payload = result.payload
                if (
                    payload.get("is_blurry")
                    or payload.get("is_underexposed")
                    or payload.get("is_overexposed")
                ):
                    photo_ids.append(result.photo_id)
            if len(page) < _PAGE_SIZE:
                return photo_ids
            offset += _PAGE_SIZE

    async def _near_duplicates(self) -> list[uuid.UUID]:
        photo_ids: set[uuid.UUID] = set()
        offset = 0
        while True:
            page = await self._duplicate_members.list(limit=_PAGE_SIZE, offset=offset)
            photo_ids.update(member.photo_id for member in page)
            if len(page) < _PAGE_SIZE:
                return list(photo_ids)
            offset += _PAGE_SIZE
