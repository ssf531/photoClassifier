import uuid
from collections.abc import AsyncIterator

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
