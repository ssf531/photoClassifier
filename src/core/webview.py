import sys

import webview


def open_window(url: str) -> None:
    webview.create_window("Photo Intelligence", url)
    # Devtools stay on for the dev loop but off in a frozen release build --
    # nothing should expose a debugging console to an end user (SDD §3.14).
    webview.start(debug=not getattr(sys, "frozen", False))
