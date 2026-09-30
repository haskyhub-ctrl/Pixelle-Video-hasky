"""
Desktop launcher: runs the Stock Matcher UI in its own application window
instead of a browser tab.

    uv run --with pywebview python -m pixelle_video.stock_matcher.desktop

It starts the Streamlit server on a free local port and opens it in a native
window (pywebview, which uses Edge WebView2 on Windows). Closing the window
stops the server. Without pywebview it falls back to an Edge / Chrome "app"
window, then to the default browser.
"""

import argparse
import atexit
import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

APP_FILE = Path(__file__).resolve().parent / "app.py"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
TITLE = "Stock Matcher"


def free_port(preferred: int = 8765) -> int:
    for port in [preferred] + list(range(preferred + 1, preferred + 50)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_server(port: int, proc: subprocess.Popen, timeout: float = 90) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.3)
    return False


def start_server(port: int) -> subprocess.Popen:
    cmd = [
        sys.executable, "-m", "streamlit", "run", str(APP_FILE),
        "--server.port", str(port),
        "--server.address", "127.0.0.1",
        "--server.headless", "true",
        "--server.fileWatcherType", "none",
        "--browser.gatherUsageStats", "false",
        "--theme.base", "light",
    ]
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.Popen(cmd, cwd=PROJECT_ROOT, creationflags=creationflags)
    atexit.register(lambda: proc.poll() is None and proc.terminate())
    return proc


def open_pywebview(url: str) -> bool:
    try:
        import webview
    except ImportError:
        return False
    try:
        webview.create_window(TITLE, url, width=1400, height=900, min_size=(900, 600))
        webview.start()  # blocks until the window is closed
        return True
    except Exception as e:  # WebView2 runtime missing, etc.
        print(f"Native window unavailable ({e}); falling back to a browser window.")
        return False


def open_app_window(url: str) -> bool:
    """Chromium 'app' mode: a window without tabs or address bar."""
    candidates = ["msedge", "chrome", "google-chrome", "chromium", "chromium-browser"]
    if os.name == "nt":
        pf = [os.environ.get(k, "") for k in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
        candidates = [
            *(os.path.join(p, "Microsoft", "Edge", "Application", "msedge.exe") for p in pf if p),
            *(os.path.join(p, "Google", "Chrome", "Application", "chrome.exe") for p in pf if p),
        ] + candidates
    for exe in candidates:
        path = exe if os.path.isfile(exe) else shutil.which(exe)
        if path:
            subprocess.Popen([path, f"--app={url}", "--window-size=1400,900"])
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Stock Matcher as a desktop app")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--browser", action="store_true",
                        help="Open in a browser window instead of a native window")
    args = parser.parse_args(argv)

    port = free_port(args.port)
    url = f"http://127.0.0.1:{port}"
    print(f"Starting {TITLE} on {url} …")
    server = start_server(port)
    if not wait_for_server(port, server):
        print("The Stock Matcher server did not start. See the messages above.")
        return 1

    try:
        if not args.browser and open_pywebview(url):
            return 0  # window closed by the user
        if not open_app_window(url):
            webbrowser.open(url)
        print(f"{TITLE} is running at {url}. Close this window or press Ctrl+C to stop.")
        server.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
