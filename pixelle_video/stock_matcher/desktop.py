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
        "--theme.primaryColor", "#ff6f61",
        "--client.toolbarMode", "minimal",
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


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


def ensure_9router(timeout: float = 40) -> None:
    """
    When the LLM backend is a local 9Router, start it if it is not running so
    the user does not have to open it by hand. Opens in its own minimized
    console window, which keeps running after Stock Matcher closes.
    """
    from urllib.parse import urlparse

    try:
        from .auth_manager import AuthManager

        llm = AuthManager(env_file=PROJECT_ROOT / ".env").llm_settings()
    except Exception:
        return
    url = urlparse(llm.base_url or "")
    is_local = url.hostname in ("localhost", "127.0.0.1")
    if not (llm.enabled and is_local and (url.port or 80) == 20128):
        return
    if _port_open("127.0.0.1", 20128):
        print("9Router is already running.")
        return
    exe = shutil.which("9router")
    if not exe:
        print("9Router is not installed. Install Node.js 20+ and run:  npm install -g 9router")
        return
    print("Starting 9Router …")
    if os.name == "nt":
        subprocess.Popen(["cmd", "/c", "start", "9Router", "/min", exe], cwd=Path.home())
    else:
        subprocess.Popen([exe], cwd=Path.home(), start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_open("127.0.0.1", 20128):
            print("9Router is up at http://localhost:20128")
            return
        time.sleep(1)
    print("9Router did not answer on port 20128 yet; check its window.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Stock Matcher as a desktop app")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--browser", action="store_true",
                        help="Open in a browser window instead of a native window")
    args = parser.parse_args(argv)

    ensure_9router()
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
