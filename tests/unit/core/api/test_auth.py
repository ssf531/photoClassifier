from fastapi.testclient import TestClient

from core.api.app import create_app


def test_health_with_correct_token_returns_200() -> None:
    app = create_app(token="known-token")
    client = TestClient(app)

    response = client.get("/health", headers={"Authorization": "Bearer known-token"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_without_token_returns_401() -> None:
    app = create_app(token="known-token")
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 401


def test_health_with_wrong_token_returns_401() -> None:
    app = create_app(token="known-token")
    client = TestClient(app)

    response = client.get("/health", headers={"Authorization": "Bearer wrong-token"})

    assert response.status_code == 401
