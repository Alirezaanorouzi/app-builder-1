from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CommandResult:
    command: str
    stdout: str
    stderr: str
    exit_code: int
    background: bool = False
    command_id: str | None = None


class WorkspaceAdapter(ABC):
    """Execution backend for agent tools — never the worker host project disk for Vercel."""

    root: Path

    @abstractmethod
    def ensure(self, project_id: str, template_name: str) -> bool:
        """Prepare sandbox. Returns True if newly created (bootstrap template)."""

    @abstractmethod
    def resolve(self, path: str | None) -> Path:
        ...

    @abstractmethod
    def view_file(self, path: str) -> str:
        ...

    @abstractmethod
    def str_replace(self, path: str, old: str, new: str) -> str:
        ...

    @abstractmethod
    def insert(self, path: str, line: int, text: str) -> str:
        ...

    @abstractmethod
    def create_file(self, path: str, content: str) -> str:
        ...

    @abstractmethod
    def grep(self, pattern: str, path: str = ".") -> str:
        ...

    @abstractmethod
    def glob(self, pattern: str) -> str:
        ...

    @abstractmethod
    def run_command(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout: int = 120,
        background: bool = False,
    ) -> CommandResult:
        ...

    @abstractmethod
    def read_command_output(self, command_id: str) -> CommandResult:
        ...

    @abstractmethod
    def preview_url(self) -> str | None:
        ...

    def stop_idle(self) -> None:
        """Optional idle shutdown hook."""

    def extend_session(self) -> None:
        """Optional session TTL extension during an active run."""