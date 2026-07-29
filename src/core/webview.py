import webview


def open_window(url: str) -> None:
    webview.create_window("Photo Intelligence", url)
    webview.start(debug=True)
