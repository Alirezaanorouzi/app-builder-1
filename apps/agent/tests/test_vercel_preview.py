from worker.workspace.vercel_sync import preview_url_from_sandbox


class _Route:
    def __init__(self, port: int, url: str) -> None:
        self.port = port
        self.url = url


def test_preview_url_from_routes_property():
    class Box:
        routes = (_Route(5173, "https://preview.vercel-sandbox.dev"),)

    assert preview_url_from_sandbox(Box()) == "https://preview.vercel-sandbox.dev"


def test_preview_url_fallback_any_port():
    class Box:
        routes = (_Route(3000, "https://other.example"),)

    assert preview_url_from_sandbox(Box()) == "https://other.example"