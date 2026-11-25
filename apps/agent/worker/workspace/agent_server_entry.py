"""OpenHands Agent Server entry on the Vercel VM with tighter tool-output limits.

Uploaded to each sandbox workspace as ``.openhands/agent_server_entry.py``.
Patches terminal output caps before the agent server imports tool sessions.
"""
from __future__ import annotations

import os
import sys


def _patch_output_limits() -> None:
    try:
        limit = int(os.environ.get("OH_MAX_CMD_OUTPUT_CHARS", "12000"))
    except ValueError:
        limit = 12000
    limit = max(2000, min(limit, 30000))
    try:
        import openhands.tools.terminal.constants as terminal_constants

        terminal_constants.MAX_CMD_OUTPUT_SIZE = limit  # type: ignore[misc]
    except Exception:
        pass


def main() -> None:
    _patch_output_limits()
    port = os.environ.get("PORT", "8000")
    if len(sys.argv) <= 1:
        sys.argv = [
            "openhands.agent_server",
            "--host",
            os.environ.get("AGENT_SERVER_HOST", "0.0.0.0"),
            "--port",
            str(port),
        ]
    import openhands.agent_server.__main__ as agent_main

    agent_main.main()


if __name__ == "__main__":
    main()