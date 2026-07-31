from pydantic import BaseModel

from core.domain.search import SearchQueryRequest


class BuiltinFilterPreset(BaseModel):
    key: str
    label: str
    search_query: SearchQueryRequest


class BuiltinFilterListResponse(BaseModel):
    items: list[BuiltinFilterPreset]
