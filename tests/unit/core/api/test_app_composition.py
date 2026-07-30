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
