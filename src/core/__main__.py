import argparse
import asyncio
import threading
import time

import uvicorn

from core.composition import compose
from core.webview import open_window

HOST = "127.0.0.1"
PORT = 8756
_SERVER_READY_TIMEOUT_SECONDS = 30.0
_SERVER_READY_POLL_INTERVAL_SECONDS = 0.05


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="core")
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="run the API server only, without opening the desktop window "
        "(used by automated tests)",
    )
    return parser.parse_args()


def _wait_until_started(server: uvicorn.Server) -> None:
    """Blocks until uvicorn's own startup has bound the listening socket.
    Opening the desktop window before this would otherwise race the server
    thread -- a race a frozen build's slower cold start (antivirus scanning,
    `_MEIPASS` extraction) makes far more likely to actually lose.
    """
    deadline = time.monotonic() + _SERVER_READY_TIMEOUT_SECONDS
    while not server.started:
        if time.monotonic() > deadline:
            raise TimeoutError("core service did not start listening in time")
        time.sleep(_SERVER_READY_POLL_INTERVAL_SECONDS)


def main() -> None:
    args = _parse_args()
    app = asyncio.run(compose()).app
    print(f"core: listening on http://{HOST}:{PORT}", flush=True)
    print(f"core: launch token: {app.state.launch_token}", flush=True)

    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT))
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    if args.no_window:
        server_thread.join()
        return

    _wait_until_started(server)
    open_window(f"http://{HOST}:{PORT}")


if __name__ == "__main__":
    main()
