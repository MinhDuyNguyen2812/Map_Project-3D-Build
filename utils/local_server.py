"""
utils/local_server.py
A lightweight HTTP server that serves the project directory on localhost.
Fixes QWebEngineView restrictions on file:// scheme — map tiles and
Fetch API both work normally under http://localhost.
"""

import threading
import http.server
import os


class _SilentHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler with logging disabled."""

    def log_message(self, format, *args):
        pass  # suppress console output

    def end_headers(self):
        # Allow cross-origin requests (needed for Fetch API in QWebEngine)
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


class LocalServer:
    """
    Serves a directory over HTTP on a background thread.

    Usage:
        server = LocalServer(root_dir=".")
        server.start()
        base_url = server.base_url   # e.g. "http://localhost:8765"
        server.stop()
    """

    def __init__(self, root_dir: str = ".", port: int = 8765):
        self.root_dir = os.path.abspath(root_dir)
        self.port     = port
        self._server  = None
        self._thread  = None

    def start(self):
        """Start the HTTP server on a daemon thread."""
        os.chdir(self.root_dir)

        handler = _SilentHandler
        self._server = http.server.HTTPServer(("localhost", self.port), handler)

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        print(f"[LocalServer] Serving {self.root_dir} at {self.base_url}")

    def stop(self):
        if self._server:
            self._server.shutdown()

    @property
    def base_url(self) -> str:
        return f"http://localhost:{self.port}"

    def url_for(self, relative_path: str) -> str:
        """Return full URL for a path relative to root_dir."""
        clean = relative_path.lstrip("./").replace("\\", "/")
        return f"{self.base_url}/{clean}"