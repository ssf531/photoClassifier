import asyncio
import json
import shutil
from pathlib import Path
from typing import Any


def find_exiftool() -> Path | None:
    found = shutil.which("exiftool")
    return Path(found) if found else None


class ExifToolWriteError(Exception):
    """`exiftool` didn't report a successful write for the target path."""


def _sanitize_value(value: str) -> str:
    """The `-@ -` argfile protocol treats each stdin line as one argument;
    a literal newline in a tag value (e.g. a multi-line AI caption) would
    corrupt that framing, so it's replaced rather than passed through.
    """
    return value.replace("\n", " ").replace("\r", " ")


class ExifToolProcess:
    """One persistent `exiftool -stay_open` process (SDD §3.8, revised in v1.1).

    Not a pool: a single process handles every metadata read, batching many
    files per `-execute` round trip to amortize both process-startup and
    per-call pipe overhead.
    """

    def __init__(self, exiftool_path: Path) -> None:
        self._exiftool_path = exiftool_path
        self._process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._execute_count = 0

    async def start(self) -> None:
        if self._process is not None:
            return
        self._process = await asyncio.create_subprocess_exec(
            str(self._exiftool_path),
            "-stay_open",
            "True",
            "-@",
            "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def read_metadata(self, path: Path) -> dict[str, Any]:
        results = await self.read_metadata_batch([path])
        return results[0] if results else {}

    async def read_metadata_batch(self, paths: list[Path]) -> list[dict[str, Any]]:
        if not paths:
            return []

        # -n: numeric/no-print-conv output, so callers get raw values
        # (e.g. 35.0, not "35.0 mm") instead of human-formatted strings.
        command_lines = ["-json", "-n", *[str(p) for p in paths]]
        output = await self._execute(command_lines)
        parsed: list[dict[str, Any]] = json.loads(output) if output.strip() else []
        return parsed

    async def write_tags(self, path: Path, tags: dict[str, str | int | list[str]]) -> None:
        """Writes `tags` to `path` (SDD §4.10's `export_xmp()`). Callers
        must pass a sidecar path here, never an original photo's path --
        there is no separate read-only mode, so which path is given IS the
        safety mechanism. Creates a new file if `path` doesn't exist yet
        (exiftool can synthesize a standalone XMP sidecar from tag values
        alone). List-valued tags (e.g. keywords) replace any existing
        value on re-export rather than accumulating duplicates -- `-Tag+=`
        alone only appends, so an existing list is cleared first in a
        separate round trip (exiftool doesn't apply a `-Tag=` clear
        together with `-Tag+=` appends for the same tag in one
        invocation; verified experimentally, not documented behavior).
        """
        list_tag_names = [key for key, value in tags.items() if isinstance(value, list)]
        if list_tag_names and path.is_file():
            await self._write_command(path, [f"-{name}=" for name in list_tag_names])

        args: list[str] = []
        for key, value in tags.items():
            if isinstance(value, list):
                args.extend(f"-{key}+={_sanitize_value(item)}" for item in value)
            else:
                args.append(f"-{key}={_sanitize_value(str(value))}")
        await self._write_command(path, args)

    async def _write_command(self, path: Path, args: list[str]) -> None:
        output = await self._execute(["-overwrite_original", *args, str(path)])
        summary = output.decode(errors="replace")
        if "1 image files created" not in summary and "1 image files updated" not in summary:
            raise ExifToolWriteError(
                f"exiftool did not report success writing {path}: {summary.strip()!r}"
            )

    async def _execute(self, command_lines: list[str]) -> bytes:
        async with self._lock:
            await self.start()
            process = self._process
            assert process is not None
            assert process.stdin is not None
            assert process.stdout is not None

            self._execute_count += 1
            marker = f"{self._execute_count:04d}"
            full_command = [*command_lines, f"-execute{marker}"]
            process.stdin.write(("\n".join(full_command) + "\n").encode())
            await process.stdin.drain()

            ready_marker = f"{{ready{marker}}}".encode()
            output = b""
            while ready_marker not in output:
                chunk = await process.stdout.readline()
                if not chunk:
                    break
                output += chunk

            return output.split(ready_marker)[0]

    async def stop(self) -> None:
        process = self._process
        if process is None:
            return
        self._process = None
        assert process.stdin is not None
        try:
            process.stdin.write(b"-stay_open\nFalse\n")
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        await process.wait()
