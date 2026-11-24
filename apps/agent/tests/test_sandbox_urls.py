from __future__ import annotations

from types import SimpleNamespace

from worker.agent_constants import AGENT_SERVER_PORT, PREVIEW_PORT
from worker.workspace.vercel_sync import agent_server_url_from_sandbox, preview_url_from_sandbox


def test_url_by_port():
    routes = (
        SimpleNamespace(port=PREVIEW_PORT, url="https://preview.example"),
        SimpleNamespace(port=AGENT_SERVER_PORT, url="https://agent.example"),
    )
    sandbox = SimpleNamespace(routes=routes)
    assert preview_url_from_sandbox(sandbox) == "https://preview.example"
    assert agent_server_url_from_sandbox(sandbox) == "https://agent.example"