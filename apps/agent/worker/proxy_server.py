"""Serve the LLM proxy on the worker's public HTTP port.

The Vercel sandbox calls this process. The same process forwards each chunk to
Liara and writes that call's cost. No separate app.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_PROXY_DIR = Path(__file__).resolve().parents[3] / "services" / "llm-proxy"


def start_proxy_server(port: int) -> None:
    if port <= 0:
        logger.warning("LLM proxy disabled (HEALTH_HTTP_PORT=%s)", port)
        return
    if not _PROXY_DIR.is_dir():
        logger.error("LLM proxy directory missing: %s", _PROXY_DIR)
        return
    proxy_path = str(_PROXY_DIR)
    if proxy_path not in sys.path:
        sys.path.insert(0, proxy_path)

    import uvicorn
    from app import app as proxy_app

    config = uvicorn.Config(
        proxy_app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, name="llm-proxy", daemon=True).start()

    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
            if response.status_code == 200:
                logger.info("LLM proxy listening on 0.0.0.0:%s", port)
                return
        except Exception:
            time.sleep(0.2)
    logger.error("LLM proxy did not become ready on port %s", port)
