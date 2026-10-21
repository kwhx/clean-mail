#!/usr/bin/env python3
"""
CleanMail Desktop Application Launcher
Wraps the local FastAPI engine in a native OS WebView window.
Works cross-platform on Windows (WebView2), macOS (WebKit), and Linux (WebKitGTK).
"""

import os
import sys
import time
import socket
import threading
import tempfile
from pathlib import Path

# Setup temporary and data directories before importing app modules
ROOT_DIR = Path(__file__).resolve().parent
TMP_DIR = ROOT_DIR / "data" / "tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)
os.environ["TMPDIR"] = str(TMP_DIR)
tempfile.tempdir = str(TMP_DIR)

import uvicorn
import webview
from app.config import get_gemini_api_key, set_gemini_api_key, HOST, PORT
from app.main import app

def find_available_port(preferred_port: int = 8000) -> int:
    """Check if preferred port is free; otherwise find an ephemeral available port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred_port))
            return preferred_port
        except OSError:
            pass

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def run_background_server(port: int):
    """Run uvicorn server in a background thread."""
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False
    )
    server = uvicorn.Server(config)
    server.run()

def wait_for_server(port: int, timeout: float = 8.0) -> bool:
    """Poll localhost until the HTTP server is ready to accept requests."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.08)
    return False

def main():
    target_port = find_available_port(PORT)

    # Launch local FastAPI server in background daemon thread
    server_thread = threading.Thread(
        target=run_background_server,
        args=(target_port,),
        daemon=True,
        name="CleanMail-Backend"
    )
    server_thread.start()

    # Block until server is responsive
    if not wait_for_server(target_port):
        print(f"Error: Local CleanMail server failed to initialize on port {target_port}.")
        sys.exit(1)

    app_url = f"http://127.0.0.1:{target_port}"

    # Create native desktop window running the OS webview
    window = webview.create_window(
        title="CleanMail",
        url=app_url,
        width=1400,
        height=850,
        min_size=(1024, 680),
        text_select=True,
        confirm_close=False,
    )

    # Start the desktop window event loop
    webview.start()

if __name__ == "__main__":
    main()
