from enum import Enum

from pydantic import BaseModel

from core.domain.library import PhotoId


class RecommendationCategory(str, Enum):  # noqa: UP042 -- kept pre-StrEnum pending broader migration
    """The v1 suggestion categories the Recommendation Engine can actually
    support with existing signals (SDD §10.2; scope matched to TASK-080's
    confirmed v1 filter set). "Daily snapshots" and "burst groups", named
    only in FEAT-073's illustrative purpose text, have no defined detection
    signal anywhere in the SDD or tag vocabulary and are deliberately not
    implemented -- inventing one would be undocumented scope, not a spec.
    """

    SCREENSHOTS = "screenshots"
    LOW_QUALITY = "low_quality"
    NEAR_DUPLICATES = "near_duplicates"


class Recommendation(BaseModel):
    category: RecommendationCategory
    photo_ids: list[PhotoId]


class RecommendationListResponse(BaseModel):
    items: list[Recommendation]
