import asyncio
import json
import shutil
from pathlib import Path
from typing import Any


def find_exiftool() -> Path | None:
    found = shutil.which("exiftool")
    return Path(found) if found else None


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

        async with self._lock:
            await self.start()
            process = self._process
            assert process is not None
            assert process.stdin is not None
            assert process.stdout is not None

            self._execute_count += 1
            marker = f"{self._execute_count:04d}"
            # -n: numeric/no-print-conv output, so callers get raw values
            # (e.g. 35.0, not "35.0 mm") instead of human-formatted strings.
            command_lines = ["-json", "-n", *[str(p) for p in paths], f"-execute{marker}"]
            process.stdin.write(("\n".join(command_lines) + "\n").encode())
            await process.stdin.drain()

            ready_marker = f"{{ready{marker}}}".encode()
            output = b""
            while ready_marker not in output:
                chunk = await process.stdout.readline()
                if not chunk:
                    break
                output += chunk

            json_part = output.split(ready_marker)[0]
            parsed: list[dict[str, Any]] = json.loads(json_part) if json_part.strip() else []
            return parsed

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
