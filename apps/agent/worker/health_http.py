"""Minimal HTTP listener for PaaS health checks (Liara Docker port)."""

from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)


def start_health_server(port: int) -> None:
    if port <= 0:
        return

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path in ("/", "/health", "/ready"):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"ok")
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, fmt: str, *args) -> None:
            logger.debug("health_http " + fmt, *args)

    def _serve() -> None:
        server = HTTPServer(("0.0.0.0", port), _Handler)
        logger.info("Health HTTP listening on 0.0.0.0:%s", port)
        server.serve_forever()

    threading.Thread(target=_serve, name="health-http", daemon=True).start()