import logging
import re
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from typing import Any, cast

import structlog

_WINDOWS_ABS_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_UNC_PATH = re.compile(r"^\\\\")
_POSIX_ABS_PATH = re.compile(r"^/[^/]+/")

_ABOVE_DEBUG_METHODS = {"info", "warning", "error", "critical"}
_REDACTED_PATH = "<redacted:path>"


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
