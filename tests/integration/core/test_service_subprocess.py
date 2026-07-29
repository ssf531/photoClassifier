import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[3]
STARTUP_TIMEOUT_SECONDS = 15.0


def test_core_service_subprocess_health_check() -> None:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        [sys.executable, "-m", "core", "--no-window"],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    lines: queue.Queue[str] = queue.Queue()
    reader = threading.Thread(target=_pump_lines, args=(process, lines), daemon=True)
    reader.start()

    try:
        port, token = _read_port_and_token(lines)
        base_url = f"http://127.0.0.1:{port}"
        _wait_until_ready(base_url)

        with httpx.Client(base_url=base_url) as client:
            authorized = client.get("/health", headers={"Authorization": f"Bearer {token}"})
            unauthorized = client.get("/health")

        assert authorized.status_code == 200
        assert authorized.json() == {"status": "ok"}
        assert unauthorized.status_code == 401
    finally:
        process.terminate()
        process.wait(timeout=10)


def _pump_lines(process: subprocess.Popen[str], lines: queue.Queue[str]) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        lines.put(line)


def _read_port_and_token(lines: queue.Queue[str]) -> tuple[str, str]:
    port: str | None = None
    token: str | None = None
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            line = lines.get(timeout=remaining)
        except queue.Empty:
            break
        port_match = re.search(r"listening on http://127\.0\.0\.1:(\d+)", line)
        if port_match:
            port = port_match.group(1)
        token_match = re.search(r"launch token: (\S+)", line)
        if token_match:
            token = token_match.group(1)
        if port and token:
            return port, token
    raise TimeoutError("core service did not print port/token in time")


def _wait_until_ready(base_url: str) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    with httpx.Client(base_url=base_url) as client:
        while time.monotonic() < deadline:
            try:
                client.get("/health")
                return
            except httpx.ConnectError:
                time.sleep(0.1)
    raise TimeoutError("core service did not become ready in time")
