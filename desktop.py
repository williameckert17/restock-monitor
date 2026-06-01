#!/usr/bin/env python3
"""
Pokepad desktop entry point.

Starts the FastAPI server on a free localhost port in a background thread,
polls until it's reachable, then opens a native pywebview window.
Closing the window signals uvicorn to exit cleanly.

Usage:
    python desktop.py

Build a native .app / .exe:
    pyinstaller pokepad.spec
"""
import socket
import sys
import threading
import time
from typing import Optional

import uvicorn
import webview
from dotenv import load_dotenv

from web.paths import APP_DATA_DIR, ENV_PATH

APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(ENV_PATH, override=True)


# ── Port helpers ─────────────────────────────────────────────────────────────

def _free_port() -> int:
    """Bind to port 0 and let the OS pick a free one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_ready(port: int, timeout: float = 15.0) -> bool:
    """Poll until the server accepts connections or timeout elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False


# ── Uvicorn wrapper ──────────────────────────────────────────────────────────

class _Server:
    def __init__(self, port: int) -> None:
        self._port = port
        self._uvicorn: Optional[uvicorn.Server] = None

    def run(self) -> None:
        config = uvicorn.Config(
            "web.app:app",
            host="127.0.0.1",
            port=self._port,
            log_level="warning",
        )
        self._uvicorn = uvicorn.Server(config)
        self._uvicorn.run()

    def stop(self) -> None:
        """Called from the pywebview closed event — signals uvicorn to exit."""
        if self._uvicorn:
            self._uvicorn.should_exit = True


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    port = _free_port()
    server = _Server(port)

    # Server runs in a daemon thread; it dies automatically if the process exits
    t = threading.Thread(target=server.run, daemon=True, name="uvicorn")
    t.start()

    if not _wait_ready(port):
        sys.exit("Pokepad: server did not become ready within 15 s")

    url = f"http://127.0.0.1:{port}"

    window = webview.create_window(
        title="Pokepad",
        url=url,
        width=1280,
        height=820,
        min_size=(960, 640),
        background_color="#0d1a06",   # matches --gb-screen; hides white flash on load
        text_select=False,
    )

    # Clean shutdown: stop uvicorn when the user closes the window
    window.events.closed += server.stop

    webview.start()


if __name__ == "__main__":
    main()
