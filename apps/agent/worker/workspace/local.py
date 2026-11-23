from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import shutil
import subprocess
import threading
import uuid
from pathlib import Path

from worker.workspace.base import CommandResult, WorkspaceAdapter
from worker.workspace.resolve import PathTraversalError, resolve_path


class LocalWorkspace(WorkspaceAdapter):
    def __init__(self, data_root: str, project_id: str, templates_dir: str | None = None) -> None:
        self.root = Path(data_root) / "sandboxes" / project_id
        self.root.mkdir(parents=True, exist_ok=True)
        self.templates_dir = Path(templates_dir) if templates_dir else Path(__file__).resolve().parents[4] / "templates"
        self._bg: dict[str, subprocess.Popen[str]] = {}
        self._preview_url: str | None = None

    def ensure(self, project_id: str, template_name: str) -> bool:
        marker = self.root / ".bootstrapped"
        if marker.exists():
            return False
        template = self.templates_dir / template_name
        if template.is_dir():
            for item in template.iterdir():
                dest = self.root / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)
        marker.write_text("ok", encoding="utf-8")
        return True

    def resolve(self, path: str | None) -> Path:
        try:
            return resolve_path(self.root, path or ".")
        except PathTraversalError as e:
            raise ValueError(str(e)) from e

    def view_file(self, path: str) -> str:
        p = self.resolve(path)
        if not p.is_file():
            return f"Error: not a file: {path}"
        return p.read_text(encoding="utf-8", errors="replace")

    def str_replace(self, path: str, old: str, new: str) -> str:
        p = self.resolve(path)
        if not p.is_file():
            return f"Error: file not found: {path}"
        text = p.read_text(encoding="utf-8")
        if old not in text:
            return "Error: str_replace pattern not found"
        p.write_text(text.replace(old, new, 1), encoding="utf-8")
        return "OK"

    def insert(self, path: str, line: int, text: str) -> str:
        p = self.resolve(path)
        if not p.is_file():
            return f"Error: file not found: {path}"
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
        idx = max(0, min(line, len(lines)))
        lines.insert(idx, text if text.endswith("\n") else text + "\n")
        p.write_text("".join(lines), encoding="utf-8")
        return "OK"

    def create_file(self, path: str, content: str) -> str:
        p = self.resolve(path)
        if p.exists():
            return f"Error: already exists: {path}"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return "OK"

    def grep(self, pattern: str, path: str = ".") -> str:
        base = self.resolve(path)
        rx = re.compile(pattern)
        lines_out: list[str] = []
        cap = 200
        for fp in base.rglob("*") if base.is_dir() else [base]:
            if not fp.is_file() or cap <= 0:
                continue
            try:
                for i, line in enumerate(fp.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if rx.search(line):
                        rel = fp.relative_to(self.root)
                        lines_out.append(f"{rel}:{i}:{line[:200]}")
                        cap -= 1
            except OSError:
                continue
        return "\n".join(lines_out) or "(no matches)"

    def glob(self, pattern: str) -> str:
        matches = []
        for p in self.root.rglob("*"):
            rel = str(p.relative_to(self.root)).replace("\\", "/")
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(p.name, pattern):
                matches.append(rel)
        return "\n".join(sorted(matches)[:500])

    def run_command(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout: int = 120,
        background: bool = False,
    ) -> CommandResult:
        work = self.resolve(cwd or ".")
        if background:
            cid = uuid.uuid4().hex
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=work,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self._bg[cid] = proc

            def _wait() -> None:
                proc.wait()

            threading.Thread(target=_wait, daemon=True).start()
            return CommandResult(command, "", "", 0, background=True, command_id=cid)
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=work,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            out, err = self._clip(completed.stdout), self._clip(completed.stderr)
            return CommandResult(command, out, err, completed.returncode)
        except subprocess.TimeoutExpired:
            return CommandResult(command, "", f"timeout after {timeout}s", 124)

    def read_command_output(self, command_id: str) -> CommandResult:
        proc = self._bg.get(command_id)
        if not proc:
            return CommandResult("", "", "unknown command_id", 1)
        out, err = proc.communicate(timeout=0.1) if proc.poll() is None else proc.communicate()
        return CommandResult(
            "",
            self._clip(out or ""),
            self._clip(err or ""),
            proc.returncode or 0,
        )

    def _preview_port(self) -> int:
        override = os.environ.get("LOCAL_PREVIEW_PORT")
        if override:
            return int(override)
        port_file = self.root / ".preview_port"
        if port_file.is_file():
            return int(port_file.read_text(encoding="utf-8").strip())
        port = 5200 + int(hashlib.md5(self.root.name.encode()).hexdigest()[:4], 16) % 800
        port_file.write_text(str(port), encoding="utf-8")
        return port

    def _ensure_dev_server(self) -> str | None:
        if self._preview_url:
            return self._preview_url
        explicit = os.environ.get("LOCAL_PREVIEW_URL")
        if explicit:
            self._preview_url = explicit
            return self._preview_url
        if not (self.root / "package.json").is_file():
            return None
        port = self._preview_port()
        marker = self.root / ".dev_server"
        if marker.is_file() and not marker.read_text(encoding="utf-8").strip().startswith("failed"):
            self._preview_url = f"http://127.0.0.1:{port}"
            return self._preview_url
        if not (self.root / "node_modules").is_dir():
            install = self.run_command("npm install", timeout=300)
            if install.exit_code != 0:
                marker.write_text(f"failed:npm install\n{install.stderr[:500]}", encoding="utf-8")
                return None
        env = {**os.environ, "PORT": str(port)}
        proc = subprocess.Popen(
            "npm run dev",
            shell=True,
            cwd=self.root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        marker.write_text(str(proc.pid), encoding="utf-8")
        self._preview_url = f"http://127.0.0.1:{port}"
        return self._preview_url

    def preview_url(self) -> str | None:
        return self._ensure_dev_server()

    @staticmethod
    def _clip(text: str, limit: int = 8192) -> str:
        if len(text) <= limit:
            return text
        return text[-limit:] + "\n…[output clipped]"

    def stop_idle(self) -> None:
        pass

    def extend_session(self) -> None:
        pass