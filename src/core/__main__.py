import argparse
import asyncio
import threading

import uvicorn

from core.composition import compose
from core.webview import open_window

HOST = "127.0.0.1"
PORT = 8756


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="core")
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="run the API server only, without opening the desktop window "
        "(used by automated tests)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    app = asyncio.run(compose()).app
    print(f"core: listening on http://{HOST}:{PORT}", flush=True)
    print(f"core: launch token: {app.state.launch_token}", flush=True)

    server_thread = threading.Thread(
        target=uvicorn.run,
        args=(app,),
        kwargs={"host": HOST, "port": PORT},
        daemon=True,
    )
    server_thread.start()

    if args.no_window:
        server_thread.join()
        return

    open_window(f"http://{HOST}:{PORT}")


if __name__ == "__main__":
    main()
