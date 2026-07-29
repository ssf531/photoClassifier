from fastapi.testclient import TestClient

from core.api.app import create_app
from core.domain.version import CORE_API_VERSION


def test_version_endpoint_returns_core_api_version() -> None:
    app = create_app(token="known-token")
    client = TestClient(app)

    response = client.get("/version", headers={"Authorization": "Bearer known-token"})

    assert response.status_code == 200
    assert response.json() == {"core_api_version": CORE_API_VERSION}


def test_version_endpoint_requires_auth() -> None:
    app = create_app(token="known-token")
    client = TestClient(app)

    response = client.get("/version")

    assert response.status_code == 401


def test_openapi_metadata_exposes_core_api_version() -> None:
    app = create_app(token="known-token")
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.json()["info"]["version"] == CORE_API_VERSION
