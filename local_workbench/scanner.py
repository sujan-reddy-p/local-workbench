"""Read-only discovery of supported files in a user-selected workspace."""

from __future__ import annotations

import os
import stat
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
            suffix = path.suffix.lower()
            kind = "text" if suffix in TEXT_EXTENSIONS else "image" if suffix in IMAGE_EXTENSIONS else ""
            if not kind:
                continue
            try:
                file_stat = path.lstat()
                if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            items.append(WorkItem(path=path, relative_path=path.relative_to(root).as_posix(), kind=kind))
    return items


def read_item(item: WorkItem) -> str | bytes:
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(item.path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"Workspace item is no longer a regular file: {item.relative_path}")
        with os.fdopen(descriptor, "rb") as source:
            descriptor = -1
            data = source.read(MAX_FILE_BYTES + 1)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"Workspace item exceeds {MAX_FILE_BYTES} bytes: {item.relative_path}")
    if item.kind == "image":
        return data
    return data[: MAX_TEXT_CHARS * 4].decode("utf-8", errors="replace")[:MAX_TEXT_CHARS]
