import uuid

from fastapi.testclient import TestClient

from core.api.app import create_app
from core.domain.problems import ProblemGroup, ProblemItem

TOKEN = "known-token"


class _FakeProblemsService:
    def __init__(self) -> None:
        self.groups: list[ProblemGroup] = []
        self.retried_photo_ids: list[uuid.UUID] = []
        self.ignored_photo_ids: list[uuid.UUID] = []
        self.retry_job_id = uuid.uuid4()

    async def list_problems(self) -> list[ProblemGroup]:
        return self.groups

    async def retry(self, photo_ids: list[uuid.UUID]) -> uuid.UUID:
        self.retried_photo_ids = list(photo_ids)
        return self.retry_job_id

    async def ignore(self, photo_ids: list[uuid.UUID]) -> None:
        self.ignored_photo_ids = list(photo_ids)


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_list_problems_requires_auth() -> None:
    app = create_app(token=TOKEN, problems_service=_FakeProblemsService())
    client = TestClient(app)

    response = client.get("/api/v1/problems")

    assert response.status_code == 401


def test_list_problems_returns_groups_from_the_service() -> None:
    service = _FakeProblemsService()
    photo_id = uuid.uuid4()
    service.groups = [
        ProblemGroup(
            error_code="provider_error",
            items=[ProblemItem(photo_id=photo_id, error_message="boom")],
        )
    ]
    app = create_app(token=TOKEN, problems_service=service)
    client = TestClient(app)

    response = client.get("/api/v1/problems", headers=_auth_headers())

    assert response.status_code == 200
    assert response.json() == {
        "groups": [
            {
                "error_code": "provider_error",
                "items": [{"photo_id": str(photo_id), "error_message": "boom"}],
            }
        ]
    }


def test_list_problems_returns_503_when_not_configured() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.get("/api/v1/problems", headers=_auth_headers())

    assert response.status_code == 503


def test_retry_problems_requires_auth() -> None:
    app = create_app(token=TOKEN, problems_service=_FakeProblemsService())
    client = TestClient(app)

    response = client.post("/api/v1/problems/retry", json={"photo_ids": []})

    assert response.status_code == 401


def test_retry_problems_enqueues_and_returns_the_job_id() -> None:
    service = _FakeProblemsService()
    app = create_app(token=TOKEN, problems_service=service)
    client = TestClient(app)
    photo_id = str(uuid.uuid4())

    response = client.post(
        "/api/v1/problems/retry",
        json={"photo_ids": [photo_id]},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"job_id": str(service.retry_job_id)}
    assert service.retried_photo_ids == [uuid.UUID(photo_id)]


def test_retry_problems_returns_503_when_not_configured() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.post(
        "/api/v1/problems/retry", json={"photo_ids": []}, headers=_auth_headers()
    )

    assert response.status_code == 503


def test_ignore_problems_requires_auth() -> None:
    app = create_app(token=TOKEN, problems_service=_FakeProblemsService())
    client = TestClient(app)

    response = client.post("/api/v1/problems/ignore", json={"photo_ids": []})

    assert response.status_code == 401


def test_ignore_problems_marks_the_requested_photos() -> None:
    service = _FakeProblemsService()
    app = create_app(token=TOKEN, problems_service=service)
    client = TestClient(app)
    photo_id = str(uuid.uuid4())

    response = client.post(
        "/api/v1/problems/ignore",
        json={"photo_ids": [photo_id]},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert service.ignored_photo_ids == [uuid.UUID(photo_id)]


def test_ignore_problems_returns_503_when_not_configured() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.post(
        "/api/v1/problems/ignore", json={"photo_ids": []}, headers=_auth_headers()
    )

    assert response.status_code == 503
