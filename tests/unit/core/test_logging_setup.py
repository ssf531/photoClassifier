import asyncio
import json

import pytest
import structlog

import core.logging_setup as logging_setup
from core.logging_setup import (
    bind_context,
    configure_logging,
    get_logger,
    get_recent_log_lines,
    redact_paths_in_text,
)


@pytest.fixture(autouse=True)
def _reset_structlog() -> None:
    structlog.contextvars.clear_contextvars()
    logging_setup._recent_log_lines.clear()
    yield
    structlog.contextvars.clear_contextvars()
    structlog.reset_defaults()
    logging_setup._recent_log_lines.clear()


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


def test_get_recent_log_lines_captures_logged_events() -> None:
    configure_logging(json_output=True, level="INFO")
    log = get_logger()

    log.info("photo.scanned", photo_id="abc")

    lines = get_recent_log_lines()
    assert len(lines) == 1
    assert "photo.scanned" in lines[0]
    assert "abc" in lines[0]


def test_get_recent_log_lines_reflects_info_level_redaction() -> None:
    """The diagnostics bundle's recent-log buffer (SDD §16.5) has no log
    file to read from -- it's captured in-process, after the same
    path-redaction rule the console renderer applies."""
    configure_logging(json_output=True, level="DEBUG")
    log = get_logger()
    windows_path = "C:\\Users\\alice\\Pictures\\a.jpg"

    log.info("photo.scanned", path=windows_path)

    lines = get_recent_log_lines()
    assert windows_path not in lines[0]
    assert "<redacted:path>" in lines[0]


def test_redact_paths_in_text_scrubs_embedded_windows_and_posix_paths() -> None:
    text = "opening C:\\Users\\alice\\Pictures\\a.jpg and /home/alice/library/b.jpg now"

    redacted = redact_paths_in_text(text)

    assert "alice" not in redacted
    assert redacted.count("<redacted:path>") == 2


def test_redact_paths_in_text_leaves_ordinary_text_untouched() -> None:
    text = "a dog on the beach, confidence 0.83"

    assert redact_paths_in_text(text) == text
