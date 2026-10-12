import os
from pathlib import Path

import pytest

from local_workbench.scanner import (
    MAX_FILE_BYTES,
    MAX_TEXT_CHARS,
    WorkItem,
    read_item,
    scan_workspace,
)


def test_scanner_filters_hidden_unsupported_large_and_symlinked_inputs(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("hello", encoding="utf-8")
    (tmp_path / "picture.jpg").write_bytes(b"image")
    (tmp_path / "movie.mp4").write_bytes(b"not analyzed")
    large = tmp_path / "large.txt"
    with large.open("wb") as source:
        source.truncate(MAX_FILE_BYTES + 1)
    hidden = tmp_path / ".private"
    hidden.mkdir()
    (hidden / "secret.txt").write_text("hidden", encoding="utf-8")
    deps = tmp_path / "node_modules"
    deps.mkdir()
    (deps / "package.json").write_text("{}", encoding="utf-8")
    target = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    target.write_text("outside", encoding="utf-8")
    try:
        (tmp_path / "link.txt").symlink_to(target)
    except OSError:
        pass

    items = scan_workspace(tmp_path)

    assert [(item.relative_path, item.kind) for item in items] == [
        ("notes.md", "text"), ("picture.jpg", "image")
    ]


def test_scanner_rejects_non_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("text", encoding="utf-8")
    try:
        scan_workspace(file_path)
    except ValueError as exc:
        assert "not a directory" in str(exc)
    else:
        raise AssertionError("expected a non-directory workspace to be rejected")


def test_reader_enforces_size_and_text_boundaries(tmp_path: Path) -> None:
    text_path = tmp_path / "notes.txt"
    text_path.write_text("x" * (MAX_TEXT_CHARS + 500), encoding="utf-8")
    text_item = WorkItem(path=text_path, relative_path="notes.txt", kind="text")
    assert read_item(text_item) == "x" * MAX_TEXT_CHARS

    large_path = tmp_path / "large.txt"
    with large_path.open("wb") as source:
        source.truncate(MAX_FILE_BYTES + 1)
    large_item = WorkItem(path=large_path, relative_path="large.txt", kind="text")
    with pytest.raises(ValueError, match="exceeds"):
        read_item(large_item)


def test_scanner_and_reader_reject_fifo_inputs(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("named pipes are not supported on this platform")
    pipe = tmp_path / "input.txt"
    os.mkfifo(pipe)

    assert scan_workspace(tmp_path) == []
    item = WorkItem(path=pipe, relative_path="input.txt", kind="text")
    with pytest.raises(ValueError, match="no longer a regular file"):
        read_item(item)
