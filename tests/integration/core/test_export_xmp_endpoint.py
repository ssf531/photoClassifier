import uuid

from fastapi.testclient import TestClient

from core.api.app import create_app
from core.domain.export import ExportResultItem

TOKEN = "known-token"


class _FakeXmpExportManager:
    """A real `ExifToolProcess`-backed manager can't be exercised through
    `TestClient`: its subprocess transport is bound to whichever event loop
    first uses it, and `TestClient` runs the ASGI app on a separate loop/
    thread (an anyio blocking portal) than an async pytest fixture's --
    the resulting cross-loop read raises `RuntimeError: ... attached to a
    different loop`. The real subprocess behavior (writing/creating
    sidecars, never touching originals) is already covered directly,
    without TestClient, in test_xmp_export_manager.py; this fake verifies
    only the endpoint's own request/response wiring.
    """

    def __init__(self) -> None:
        self.received_photo_ids: list[uuid.UUID] = []

    async def export_xmp(self, photo_ids: list[uuid.UUID]) -> list[ExportResultItem]:
        self.received_photo_ids = list(photo_ids)
        return [ExportResultItem(photo_id=photo_id, success=True) for photo_id in photo_ids]


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_export_xmp_requires_auth() -> None:
    app = create_app(token=TOKEN, xmp_export_manager=_FakeXmpExportManager())
    client = TestClient(app)
    photo_id = str(uuid.uuid4())

    response = client.post("/api/v1/export/xmp", json={"photo_ids": [photo_id]})

    assert response.status_code == 401


def test_export_xmp_passes_photo_ids_through_and_reports_the_result() -> None:
    manager = _FakeXmpExportManager()
    app = create_app(token=TOKEN, xmp_export_manager=manager)
    client = TestClient(app)
    photo_id = str(uuid.uuid4())

    response = client.post(
        "/api/v1/export/xmp",
        json={"photo_ids": [photo_id]},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["items"] == [{"photo_id": photo_id, "success": True, "error": None}]
    assert manager.received_photo_ids == [uuid.UUID(photo_id)]


def test_export_xmp_returns_503_when_not_configured() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.post("/api/v1/export/xmp", json={"photo_ids": []}, headers=_auth_headers())

    assert response.status_code == 503
