"""Read-only discovery of supported files in a user-selected workspace."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

TEXT_EXTENSIONS = {".md", ".txt", ".csv", ".tsv", ".json", ".yaml", ".yml", ".xml", ".html", ".log", ".ini", ".toml", ".py"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
IGNORED_DIRS = {".git", ".venv", ".local-workbench", "node_modules", "__pycache__"}
MAX_FILES = 1000
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 32_000


@dataclass(frozen=True)
class WorkItem:
    path: Path
    relative_path: str
    kind: str


def scan_workspace(workspace: Path) -> list[WorkItem]:
    root = workspace.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"Workspace is not a directory: {root}")
    items: list[WorkItem] = []
    for directory, dirs, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(directory)
        dirs[:] = sorted(
            name for name in dirs
            if name not in IGNORED_DIRS and not name.startswith(".") and not (current / name).is_symlink()
        )
        for filename in sorted(filenames):
            if len(items) >= MAX_FILES:
                return items
            if filename.startswith("."):
                continue
            path = current / filename
            if path.is_symlink():
                continue
            suffix = path.suffix.lower()
            kind = "text" if suffix in TEXT_EXTENSIONS else "image" if suffix in IMAGE_EXTENSIONS else ""
            if not kind:
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            items.append(WorkItem(path=path, relative_path=path.relative_to(root).as_posix(), kind=kind))
    return items


def read_item(item: WorkItem) -> str | bytes:
    data = item.path.read_bytes()
    if item.kind == "image":
        return data
    return data[: MAX_TEXT_CHARS * 4].decode("utf-8", errors="replace")[:MAX_TEXT_CHARS]
