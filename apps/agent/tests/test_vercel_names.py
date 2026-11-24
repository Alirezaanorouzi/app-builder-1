import re

from worker.workspace.vercel_names import vercel_sandbox_api_name, vercel_sandbox_display_name


def test_api_name_no_colon():
    name = vercel_sandbox_api_name("dev", "f162723e-751d-42d4-a68d-73d6a3981e63")
    assert ":" not in name
    assert re.match(r"^[a-zA-Z0-9_-]+$", name)
    assert name.startswith("dev-f162723e")


def test_display_name():
    assert vercel_sandbox_display_name("dev", "abc") == "dev:abc"