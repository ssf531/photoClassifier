from fastapi.testclient import TestClient

from core.api.app import create_app

TOKEN = "known-token"


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_list_builtin_filters_requires_auth() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.get("/api/v1/builtin-filters")

    assert response.status_code == 401


def test_list_builtin_filters_returns_the_v1_presets() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.get("/api/v1/builtin-filters", headers=_auth_headers())

    assert response.status_code == 200
    keys = {item["key"] for item in response.json()["items"]}
    assert keys == {"screenshots", "blurry", "duplicates"}
