import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi.testclient import TestClient

from core.api.app import create_app
from core.domain.scheduler import JobID, JobProgress, JobSpec


class FakeScheduler:
    def __init__(self) -> None:
        self.enqueued: list[JobSpec] = []

    async def enqueue(self, job: JobSpec) -> JobID:
        self.enqueued.append(job)
        return uuid.uuid4()

    async def cancel(self, job_id: JobID) -> None:
        pass

    async def progress_stream(self) -> AsyncIterator[JobProgress]:
        return
        yield  # pragma: no cover


def test_create_app_accepts_a_fake_scheduler_without_modification() -> None:
    fake = FakeScheduler()

    app = create_app(token="known-token", scheduler=fake)

    assert app.state.scheduler is fake


def test_index_html_embeds_the_launch_token_for_the_browser_to_read(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        "<html><head><title>Photo Intelligence</title></head><body></body></html>",
        encoding="utf-8",
    )

    app = create_app(token="known-token", ui_dist_dir=tmp_path)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert 'window.__LAUNCH_TOKEN__ = "known-token";' in response.text
    assert "<title>Photo Intelligence</title>" in response.text


def test_index_html_is_not_served_when_ui_dist_dir_has_no_build(tmp_path: Path) -> None:
    app = create_app(token="known-token", ui_dist_dir=tmp_path)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 404


def test_static_assets_are_served_from_the_ui_dist_dir(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        "<html><head></head><body></body></html>", encoding="utf-8"
    )
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "app.js").write_text("console.log('hi');", encoding="utf-8")

    app = create_app(token="known-token", ui_dist_dir=tmp_path)
    client = TestClient(app)

    response = client.get("/assets/app.js")

    assert response.status_code == 200
    assert response.text == "console.log('hi');"


def test_unknown_client_side_routes_fall_back_to_index_html(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        "<html><head><title>Photo Intelligence</title></head><body></body></html>",
        encoding="utf-8",
    )

    app = create_app(token="known-token", ui_dist_dir=tmp_path)
    client = TestClient(app)

    response = client.get("/search")

    assert response.status_code == 200
    assert "<title>Photo Intelligence</title>" in response.text
    assert 'window.__LAUNCH_TOKEN__ = "known-token";' in response.text


def test_spa_fallback_rejects_path_traversal_outside_the_dist_dir(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        "<html><head><title>Photo Intelligence</title></head><body></body></html>",
        encoding="utf-8",
    )
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("do not serve me", encoding="utf-8")

    app = create_app(token="known-token", ui_dist_dir=tmp_path)
    client = TestClient(app)

    # Percent-encoded dot segments survive httpx's own URL normalization
    # (which only collapses literal ".." in the request path), so this
    # actually reaches the traversal guard rather than being harmlessly
    # rewritten to "/secret.txt" before the request is even sent.
    response = client.get("/%2e%2e/secret.txt")

    assert response.status_code == 200
    assert "do not serve me" not in response.text
    assert "<title>Photo Intelligence</title>" in response.text


def test_api_routes_still_win_over_the_spa_fallback_when_ui_is_configured(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        "<html><head></head><body></body></html>", encoding="utf-8"
    )

    app = create_app(token="known-token", ui_dist_dir=tmp_path)
    client = TestClient(app)

    response = client.get("/health", headers={"Authorization": "Bearer known-token"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
