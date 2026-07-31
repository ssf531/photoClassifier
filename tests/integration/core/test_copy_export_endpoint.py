import uuid

from fastapi.testclient import TestClient

from core.api.app import create_app
from core.domain.copy_export import CopyResultItem

TOKEN = "known-token"


class _FakeCopyExportManager:
    def __init__(self) -> None:
        self.received_photo_ids: list[uuid.UUID] = []
        self.received_destination: str | None = None

    async def copy_to_folder(
        self, photo_ids: list[uuid.UUID], destination_folder: str
    ) -> list[CopyResultItem]:
        self.received_photo_ids = list(photo_ids)
        self.received_destination = destination_folder
        return [
            CopyResultItem(
                photo_id=photo_id,
                success=True,
                destination_path=f"{destination_folder}/{photo_id}.jpg",
            )
            for photo_id in photo_ids
        ]


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_copy_to_folder_requires_auth() -> None:
    app = create_app(token=TOKEN, copy_export_manager=_FakeCopyExportManager())
    client = TestClient(app)
    photo_id = str(uuid.uuid4())

    response = client.post(
        "/api/v1/export/copy",
        json={"photo_ids": [photo_id], "destination_folder": "C:/Export"},
    )

    assert response.status_code == 401


def test_copy_to_folder_passes_photo_ids_and_destination_through() -> None:
    manager = _FakeCopyExportManager()
    app = create_app(token=TOKEN, copy_export_manager=manager)
    client = TestClient(app)
    photo_id = str(uuid.uuid4())

    response = client.post(
        "/api/v1/export/copy",
        json={"photo_ids": [photo_id], "destination_folder": "C:/Export"},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [
        {
            "photo_id": photo_id,
            "success": True,
            "destination_path": f"C:/Export/{photo_id}.jpg",
            "error": None,
        }
    ]
    assert manager.received_photo_ids == [uuid.UUID(photo_id)]
    assert manager.received_destination == "C:/Export"


def test_copy_to_folder_returns_503_when_not_configured() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.post(
        "/api/v1/export/copy",
        json={"photo_ids": [], "destination_folder": "C:/Export"},
        headers=_auth_headers(),
    )

    assert response.status_code == 503
