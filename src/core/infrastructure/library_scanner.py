import os
from collections.abc import Iterator
from fnmatch import fnmatch
from pathlib import Path

from core.domain.library import SUPPORTED_PHOTO_EXTENSIONS

_LONG_PATH_PREFIX = "\\\\?\\"


def _to_long_path(path: Path) -> Path:
    if os.name == "nt":
        raw = str(path)
        if not raw.startswith(_LONG_PATH_PREFIX):
            return Path(_LONG_PATH_PREFIX + raw)
    return path


def _matches_any_glob(relative_posix: str, patterns: list[str]) -> bool:
    return any(fnmatch(relative_posix, pattern) for pattern in patterns)


def walk(
    root: Path,
    *,
    include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
    supported_extensions: frozenset[str] = SUPPORTED_PHOTO_EXTENSIONS,
    follow_symlinks: bool = False,
) -> Iterator[Path]:
    """Recursively discover photo files under root.

    Never follows symlinks/junctions unless explicitly opted in (ADR-0010).
    Handles paths beyond MAX_PATH on Windows via `\\\\?\\` prefixing.
    """
    resolved_root = root.resolve()
    yield from _walk_dir(
        resolved_root,
        resolved_root,
        include_globs or [],
        exclude_globs or [],
        supported_extensions,
        follow_symlinks,
    )


def _walk_dir(
    root: Path,
    current: Path,
    include_globs: list[str],
    exclude_globs: list[str],
    supported_extensions: frozenset[str],
    follow_symlinks: bool,
) -> Iterator[Path]:
    try:
        entries = sorted(os.scandir(_to_long_path(current)), key=lambda e: e.name)
    except OSError:
        return

    for entry in entries:
        entry_path = current / entry.name

        if entry.is_symlink() and not follow_symlinks:
            continue

        if entry.is_dir(follow_symlinks=follow_symlinks):
            yield from _walk_dir(
                root,
                entry_path,
                include_globs,
                exclude_globs,
                supported_extensions,
                follow_symlinks,
            )
        elif entry.is_file(follow_symlinks=follow_symlinks):
            if entry_path.suffix.lower() not in supported_extensions:
                continue
            relative_posix = entry_path.relative_to(root).as_posix()
            if exclude_globs and _matches_any_glob(relative_posix, exclude_globs):
                continue
            if include_globs and not _matches_any_glob(relative_posix, include_globs):
                continue
            yield entry_path
