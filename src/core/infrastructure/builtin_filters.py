from core.domain.builtin_filters import BuiltinFilterPreset
from core.domain.search import MetadataFiltersRequest, SearchQueryRequest

# v1 ships exactly the four filters v1 data can actually support (MVP Scope
# Overlay, TASK-080): "screenshots, blurry, duplicates, similar." "similar"
# is intentionally not a preset here -- it's inherently per-photo (TASK-058's
# existing similar-image search needs a reference photo, not a one-click
# filter) rather than a library-wide smart-collection query. Receipts,
# memes, daily snapshots, and burst groups have no detection signal
# anywhere in the SDD, codebase, or tag vocabulary and are deferred to v1.1
# per the same scope note.
BUILTIN_FILTER_PRESETS: list[BuiltinFilterPreset] = [
    BuiltinFilterPreset(
        key="screenshots",
        label="Screenshots",
        search_query=SearchQueryRequest(text="screenshot", mode="text"),
    ),
    BuiltinFilterPreset(
        key="blurry",
        label="Blurry",
        search_query=SearchQueryRequest(
            mode="metadata", filters=MetadataFiltersRequest(is_blurry=True)
        ),
    ),
    BuiltinFilterPreset(
        key="duplicates",
        label="Duplicates",
        search_query=SearchQueryRequest(
            mode="metadata", filters=MetadataFiltersRequest(in_duplicate_group=True)
        ),
    ),
]
