from unittest.mock import MagicMock, patch

from worker.workspace import vercel_sync


def test_start_vite_skips_when_http_probe_succeeds():
    sandbox = MagicMock()
    with patch.object(vercel_sync, "_wait_vite_http", return_value=True):
        vercel_sync._start_vite_dev_server(sandbox)
    sandbox.run_command.assert_not_called()