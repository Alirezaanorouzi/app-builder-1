"""OpenHands SDK stores state under ``<persistence_dir>/<conversation_id.hex>``."""

from __future__ import annotations

import uuid
from pathlib import Path


def sdk_conversation_dir(persistence_base: str | Path, conversation_id: uuid.UUID) -> Path:
    return Path(persistence_base) / conversation_id.hex