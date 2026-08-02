import logging
import re
from collections import deque
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from typing import Any, cast

import structlog

_WINDOWS_ABS_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_UNC_PATH = re.compile(r"^\\\\")
_POSIX_ABS_PATH = re.compile(r"^/[^/]+/")

_ABOVE_DEBUG_METHODS = {"info", "warning", "error", "critical"}
_REDACTED_PATH = "<redacted:path>"

# Embedded (non-anchored) equivalents of the three patterns above, for
# scrubbing a path-like token that appears mid-string in already-rendered
# text (e.g. a log line) rather than as a whole event_dict value.
_WINDOWS_PATH_TOKEN = re.compile(r"[A-Za-z]:[\\/][^\s\"'<>]*")
_UNC_PATH_TOKEN = re.compile(r"\\\\[^\s\"'<>]*")
_POSIX_PATH_TOKEN = re.compile(r"(?<![\w./])/(?:[^\s\"'<>/]+/)+[^\s\"'<>]*")

_RECENT_LOG_MAXLEN = 1000
_recent_log_lines: deque[str] = deque(maxlen=_RECENT_LOG_MAXLEN)


def _looks_like_path(value: str) -> bool:
    return bool(
        _WINDOWS_ABS_PATH.match(value) or _UNC_PATH.match(value) or _POSIX_ABS_PATH.match(value)
    )


def redact_paths_above_debug(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    if method_name not in _ABOVE_DEBUG_METHODS:
        return event_dict
    for key, value in event_dict.items():
        if isinstance(value, str) and _looks_like_path(value):
            event_dict[key] = _REDACTED_PATH
    return event_dict


def redact_paths_in_text(text: str) -> str:
    """Best-effort scrub of path-like tokens embedded anywhere in free-form
    text (SDD §16.5's diagnostics bundle, no-consent default) -- broader
    than `redact_paths_above_debug`'s whole-value match, since a rendered
    log line usually has a path embedded mid-string rather than as an
    isolated value. Best-effort, not a security boundary: this is for a
    voluntary bug-report attachment, not a hard privacy control.
    """
    text = _WINDOWS_PATH_TOKEN.sub(_REDACTED_PATH, text)
    text = _UNC_PATH_TOKEN.sub(_REDACTED_PATH, text)
    return _POSIX_PATH_TOKEN.sub(_REDACTED_PATH, text)


def _capture_recent(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Buffers the most recent log entries in memory for the diagnostics
    bundle (SDD §16.5) -- there is no log file on disk to read from
    otherwise. Runs after `redact_paths_above_debug`, so captured INFO+
    entries already have whole-value paths scrubbed.
    """
    timestamp = event_dict.get("timestamp", "")
    level = event_dict.get("level", method_name)
    event = event_dict.get("event", "")
    extras = {
        key: value
        for key, value in event_dict.items()
        if key not in ("timestamp", "level", "event")
    }
    line = f"{timestamp} [{level}] {event}"
    if extras:
        line += f" {extras}"
    _recent_log_lines.append(line)
    return event_dict


def get_recent_log_lines() -> list[str]:
    return list(_recent_log_lines)


def configure_logging(*, json_output: bool, level: str = "INFO") -> None:
    renderer: Any = (
        structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            redact_paths_above_debug,
            _capture_recent,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(*args: Any, **kwargs: Any) -> structlog.stdlib.BoundLogger:
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(*args, **kwargs))


@contextmanager
def bind_context(**kwargs: Any) -> Iterator[None]:
    tokens = structlog.contextvars.bind_contextvars(**kwargs)
    try:
        yield
    finally:
        structlog.contextvars.reset_contextvars(**tokens)
