from pathlib import Path

from local_workbench.scanner import scan_workspace


def test_scanner_filters_hidden_unsupported_large_and_symlinked_inputs(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("hello", encoding="utf-8")
    (tmp_path / "picture.jpg").write_bytes(b"image")
    (tmp_path / "movie.mp4").write_bytes(b"not analyzed")
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
