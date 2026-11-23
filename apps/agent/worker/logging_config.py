"""Worker logging: keep OpenHands agent details in DB events, not the console."""

from __future__ import annotations

import logging


def configure_worker_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")
    for name in ("openhands", "openhands.sdk", "litellm", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("litellm").setLevel(logging.ERROR)