from worker.workspace.vercel_sync import _npm_install_shell


def test_npm_install_shell_approves_esbuild() -> None:
    sh = _npm_install_shell()
    assert "install-scripts approve esbuild" in sh
    assert "npm rebuild" in sh
    assert "node_modules/.bin/vite --version" in sh
    assert "NODE_ENV=development" in sh