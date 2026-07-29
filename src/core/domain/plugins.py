from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Capability(str, Enum):  # noqa: UP042 -- kept pre-StrEnum pending broader migration
    EMBEDDING = "embedding"
    CAPTION = "caption"
    TAG = "tag"
    DUPLICATE = "duplicate"
    QUALITY = "quality"


class ModelSource(str, Enum):  # noqa: UP042 -- kept pre-StrEnum pending broader migration
    BUNDLED = "bundled"
    DOWNLOAD = "download"
    USER_SUPPLIED = "user_supplied"


class AvailabilityStatus(str, Enum):  # noqa: UP042 -- kept pre-StrEnum pending broader migration
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class CapabilityAvailability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    reason: str | None = None


class PluginCompatibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core_api_version: str


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    version: str
    capability: Capability
    entry_point: Literal["inproc"]
    runtime: str
    permissions: list[str] = Field(default_factory=list)
    model_source: ModelSource
    model_filename: str | None = None
    compatibility: PluginCompatibility
