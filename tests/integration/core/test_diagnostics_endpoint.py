from fastapi.testclient import TestClient

from core.api.app import create_app

TOKEN = "known-token"


class _FakeDiagnosticsBundleBuilder:
    def __init__(self) -> None:
        self.received_include_paths: bool | None = None

    async def build(self, *, include_paths: bool) -> bytes:
        self.received_include_paths = include_paths
        return b"fake-zip-bytes"


def test_diagnostics_bundle_requires_auth() -> None:
    app = create_app(token=TOKEN, diagnostics_bundle_builder=_FakeDiagnosticsBundleBuilder())
    client = TestClient(app)

    response = client.get("/api/v1/diagnostics/bundle")

    assert response.status_code == 401


def test_diagnostics_bundle_accepts_the_token_as_a_query_param() -> None:
    """Mirrors the thumbnail endpoint's precedent: a download link (`<a
    href>`) can't send an Authorization header, so the token may also be
    passed as a query parameter."""
    app = create_app(token=TOKEN, diagnostics_bundle_builder=_FakeDiagnosticsBundleBuilder())
    client = TestClient(app)

    response = client.get(f"/api/v1/diagnostics/bundle?token={TOKEN}")

    assert response.status_code == 200


def test_diagnostics_bundle_returns_a_zip_attachment() -> None:
    builder = _FakeDiagnosticsBundleBuilder()
    app = create_app(token=TOKEN, diagnostics_bundle_builder=builder)
    client = TestClient(app)

    response = client.get(
        "/api/v1/diagnostics/bundle", headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert (
        response.headers["content-disposition"] == 'attachment; filename="diagnostics-bundle.zip"'
    )
    assert response.content == b"fake-zip-bytes"
    assert builder.received_include_paths is False


def test_diagnostics_bundle_passes_include_paths_through() -> None:
    builder = _FakeDiagnosticsBundleBuilder()
    app = create_app(token=TOKEN, diagnostics_bundle_builder=builder)
    client = TestClient(app)

    response = client.get(
        "/api/v1/diagnostics/bundle?include_paths=true",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert response.status_code == 200
    assert builder.received_include_paths is True


def test_diagnostics_bundle_returns_503_when_not_configured() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    response = client.get(
        "/api/v1/diagnostics/bundle", headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert response.status_code == 503
