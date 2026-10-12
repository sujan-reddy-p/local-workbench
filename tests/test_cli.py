from __future__ import annotations

from pathlib import Path

import pytest

from local_workbench import cli, engine
from local_workbench.store import JobStore


class FakeClient:
    def __init__(self, model: str = "") -> None:
        self.model = model

    def inspect(self, goal: str, relative_path: str, content: str | bytes) -> dict[str, object]:
        if relative_path.endswith("bad.txt"):
            raise RuntimeError("synthetic provider failure")
        return {"category": "notes", "confidence": 0.9, "summary": "synthetic result", "notes": ""}


def invoke(monkeypatch: pytest.MonkeyPatch, *args: str) -> None:
    monkeypatch.setattr(engine, "OllamaClient", FakeClient)
    monkeypatch.setattr("sys.argv", ["local-workbench", *args])
    cli.main()


def test_parallel_and_workspace_errors_are_concise(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.argv", ["local-workbench", "--parallel", "5"])
    with pytest.raises(SystemExit) as invalid_parallel:
        cli.main()
    assert invalid_parallel.value.code == 2
    assert "must be between 1 and 4" in capsys.readouterr().err

    monkeypatch.setattr("sys.argv", ["local-workbench", "--workspace", str(tmp_path / "missing"), "--task", "inspect"])
    with pytest.raises(SystemExit) as invalid_workspace:
        cli.main()
    assert invalid_workspace.value.code == 2
    assert "does not exist" in capsys.readouterr().err


@pytest.mark.parametrize("task", ["", "   "])
def test_empty_task_is_argument_error_not_tui(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], task: str
) -> None:
    monkeypatch.setattr("sys.argv", ["local-workbench", "--task", task])
    monkeypatch.setattr(cli, "run_tui", lambda *args: pytest.fail("empty task opened the TUI"))

    with pytest.raises(SystemExit) as failure:
        cli.main()

    assert failure.value.code == 2
    assert "--task must not be empty" in capsys.readouterr().err


def test_successful_direct_run_reports_counts_and_zero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    workspace = tmp_path / "workspace"
    state_dir = tmp_path / "state"
    workspace.mkdir()
    (workspace / "note.txt").write_text("hello", encoding="utf-8")
    invoke(monkeypatch, "--workspace", str(workspace), "--state-dir", str(state_dir), "--task", "inspect")
    output = capsys.readouterr().out
    assert "1/1 complete" in output

    store = JobStore(state_dir)
    run = store.get_run(1)
    assert run is not None
    assert run["status"] == "complete"
    assert store.counts(1) == {"complete": 1}
    results = store.results(1)
    assert len(results) == 1
    assert results[0]["relative_path"] == "note.txt"
    assert results[0]["status"] == "complete"
    assert results[0]["result"]["summary"] == "synthetic result"  # type: ignore[index]


def test_partial_failure_reports_needs_attention_and_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace = tmp_path / "workspace"
    state_dir = tmp_path / "state"
    workspace.mkdir()
    (workspace / "good.txt").write_text("hello", encoding="utf-8")
    (workspace / "bad.txt").write_text("fail", encoding="utf-8")
    with pytest.raises(SystemExit) as failure:
        invoke(monkeypatch, "--workspace", str(workspace), "--state-dir", str(state_dir), "--task", "inspect")
    assert failure.value.code == 1
    output = capsys.readouterr().out
    assert "needs attention" in output
    assert "1/2 complete" in output
    assert "1 failed" in output

    store = JobStore(state_dir)
    run = store.get_run(1)
    assert run is not None
    assert run["status"] == "needs-attention"
    assert store.counts(1) == {"complete": 1, "failed": 1}
    results = {str(row["relative_path"]): row for row in store.results(1)}
    assert results["good.txt"]["status"] == "complete"
    assert results["bad.txt"]["status"] == "failed"
    assert results["bad.txt"]["error"] == "synthetic provider failure"
