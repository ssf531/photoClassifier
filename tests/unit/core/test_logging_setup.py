import asyncio
import json

import pytest
import structlog

from core.logging_setup import bind_context, configure_logging, get_logger


@pytest.fixture(autouse=True)
def _reset_structlog() -> None:
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()
    structlog.reset_defaults()


def _read_json_lines(raw: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in raw.strip().splitlines() if line.strip()]


def test_path_redacted_at_info_but_not_at_debug(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(json_output=True, level="DEBUG")
    log = get_logger()
    windows_path = "C:\\Users\\alice\\Pictures\\a.jpg"

    log.info("photo.scanned", path=windows_path)
    log.debug("photo.scanned.debug", path=windows_path)

    lines = _read_json_lines(capsys.readouterr().out)
    assert lines[0]["path"] == "<redacted:path>"
    assert lines[1]["path"] == windows_path


def test_bind_context_propagates_across_asyncio_task_boundary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(json_output=True, level="INFO")
    log = get_logger()

    async def child() -> None:
        log.info("child.ran")

    async def parent() -> None:
        with bind_context(job_id="job-123"):
            await asyncio.create_task(child())

    asyncio.run(parent())

    lines = _read_json_lines(capsys.readouterr().out)
    assert lines[0]["job_id"] == "job-123"
    assert lines[0]["event"] == "child.ran"


def test_bind_context_resets_after_exit(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(json_output=True, level="INFO")
    log = get_logger()

    with bind_context(job_id="job-123"):
        pass
    log.info("outside.context")

    lines = _read_json_lines(capsys.readouterr().out)
    assert "job_id" not in lines[0]
