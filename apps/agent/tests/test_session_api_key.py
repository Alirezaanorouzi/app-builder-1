from worker.config import Settings
from worker.workspace.vercel_agent_session import _derive_session_api_key


def test_session_api_key_stable_per_project() -> None:
    settings = Settings.load()
    a = _derive_session_api_key(settings, "proj-a")
    b = _derive_session_api_key(settings, "proj-a")
    assert a == b
    if not settings.oh_session_api_key:
        c = _derive_session_api_key(settings, "proj-b")
        assert a != c