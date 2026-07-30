from pydantic import BaseModel

CORE_API_VERSION = "1.0.0"


class HealthResponse(BaseModel):
    status: str


class VersionResponse(BaseModel):
    core_api_version: str
