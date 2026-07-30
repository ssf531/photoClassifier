import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from core.api.app import create_app
from core.domain.scheduler import JobID, JobProgress, JobSpec, JobStatus

TOKEN = "known-token"


class _FixedProgressScheduler:
    """Yields a canned sequence of progress events then ends the stream --
    unlike the real scheduler's progress_stream(), which never ends until
    disconnected. Good enough to prove the WS route wires progress_stream()
    through to the client without needing a live job pipeline.
    """

    def __init__(self, events: list[JobProgress]) -> None:
        self._events = events

    async def enqueue(self, job: JobSpec) -> JobID:  # pragma: no cover
        raise NotImplementedError

    async def cancel(self, job_id: JobID) -> None:  # pragma: no cover
        raise NotImplementedError

    async def progress_stream(self) -> AsyncIterator[JobProgress]:
        for event in self._events:
            yield event


def test_job_progress_ws_streams_scheduler_events_as_json() -> None:
    job_id = uuid.uuid4()
    events = [
        JobProgress(
            job_id=job_id, job_type="analysis", status=JobStatus.RUNNING, progress_pct=42.0
        ),
        JobProgress(
            job_id=job_id, job_type="analysis", status=JobStatus.COMPLETED, progress_pct=100.0
        ),
    ]
    app = create_app(token=TOKEN, scheduler=_FixedProgressScheduler(events))
    client = TestClient(app)

    with client.websocket_connect(f"/api/v1/jobs/progress?token={TOKEN}") as ws:
        first = ws.receive_json()
        second = ws.receive_json()

    assert first == {
        "job_id": str(job_id),
        "job_type": "analysis",
        "status": "running",
        "progress_pct": 42.0,
    }
    assert second["status"] == "completed"
    assert second["progress_pct"] == 100.0


def test_job_progress_ws_rejects_a_missing_or_wrong_token() -> None:
    app = create_app(token=TOKEN, scheduler=_FixedProgressScheduler([]))
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/jobs/progress?token=wrong-token"):
            pass


def test_job_progress_ws_closes_when_no_scheduler_is_configured() -> None:
    app = create_app(token=TOKEN)
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/v1/jobs/progress?token={TOKEN}"):
            pass
