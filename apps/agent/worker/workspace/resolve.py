from __future__ import annotations

from pathlib import Path


class PathTraversalError(ValueError):
    pass


def resolve_path(root: Path, path: str | None) -> Path:
    if path is None or path == "":
        return root.resolve()
    if "\0" in path:
        raise PathTraversalError("null byte in path")
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    normalized = Path(*candidate.parts)
    try:
        resolved = normalized.resolve(strict=False)
        root_resolved = root.resolve()
        resolved.relative_to(root_resolved)
        if resolved.is_symlink():
            real = resolved.resolve()
            real.relative_to(root_resolved)
            return real
        return resolved
    except ValueError as e:
        raise PathTraversalError(str(e)) from e