from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from local_workbench import engine
from local_workbench.actions import apply_category_copies
from local_workbench.engine import run_batch
from local_workbench.store import JobStore


class DelayedProvider:
    def __init__(self, fail_first: bool = False) -> None:
        self.active = 0
        self.max_active = 0
        self.fail_first = fail_first
        self.calls: list[str] = []

    def inspect(self, goal: str, relative_path: str, content: str | bytes) -> dict[str, object]:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.calls.append(relative_path)
        try:
            time.sleep(0.02)
            if self.fail_first and len(self.calls) == 1:
                raise RuntimeError("temporary local model failure")
            return {"category": "Follow-up needed", "summary": f"{goal}: {relative_path}", "confidence": 0.93, "notes": "Checked"}
        finally:
            self.active -= 1


@pytest.mark.asyncio
async def test_batch_persists_results_respects_cap_and_leaves_sources_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first = workspace / "one.md"
    second = workspace / "two.txt"
    first.write_text("private first", encoding="utf-8")
    second.write_text("private second", encoding="utf-8")
    state = tmp_path / "state"
    provider = DelayedProvider()
    monkeypatch.setattr(engine, "_suggest_parallelism", lambda configured: min(configured, 2))

    run_id, report = await run_batch("triage follow-ups", workspace, state, max_parallel=2, provider=provider)

    store = JobStore(state)
    assert provider.max_active == 2
    assert store.counts(run_id) == {"complete": 2}
    assert "Follow-up needed" in report.read_text(encoding="utf-8")
    assert first.read_text(encoding="utf-8") == "private first"
    assert second.read_text(encoding="utf-8") == "private second"

    output, copied = apply_category_copies(state, run_id)
    assert copied == 2
    assert (output / "Follow_up_needed" / "one.md").read_text(encoding="utf-8") == "private first"
    assert (output / "Follow_up_needed" / "two.txt").read_text(encoding="utf-8") == "private second"
    existing = output / "Follow_up_needed" / "one.md"
    existing.write_text("keep this export", encoding="utf-8")
    assert apply_category_copies(state, run_id)[1] == 0
    assert existing.read_text(encoding="utf-8") == "keep this export"
    assert first.read_text(encoding="utf-8") == "private first"


@pytest.mark.asyncio
async def test_failed_work_resumes_from_sqlite_without_reprocessing_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "one.md").write_text("one", encoding="utf-8")
    (workspace / "two.md").write_text("two", encoding="utf-8")
    state = tmp_path / "state"
    monkeypatch.setattr(engine, "_suggest_parallelism", lambda configured: 1)

    failing = DelayedProvider(fail_first=True)
    run_id, _ = await run_batch("classify notes", workspace, state, provider=failing)
    assert JobStore(state).counts(run_id) == {"complete": 1, "failed": 1}

    recovery = DelayedProvider()
    resumed_id, report = await run_batch("", workspace, state, run_id=run_id, provider=recovery)

    assert resumed_id == run_id
    assert len(recovery.calls) == 1
    assert JobStore(state).counts(run_id) == {"complete": 2}
    assert "temporary local model failure" not in report.read_text(encoding="utf-8")


def test_parallelism_adapts_to_memory_and_cpu_without_exceeding_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    class Memory:
        available = 16 * 1024 ** 3

    import psutil
    monkeypatch.setattr(psutil, "virtual_memory", lambda: Memory())
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 0)
    assert engine._suggest_parallelism(2) == 2
    assert engine._suggest_parallelism(4) == 3
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 95)
    assert engine._suggest_parallelism(4) == 1
    Memory.available = 2 * 1024 ** 3
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 0)
    assert engine._suggest_parallelism(4) == 1


@pytest.mark.asyncio
async def test_adaptive_gate_rechecks_resource_budget_while_jobs_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    budget = {"slots": 2}
    monkeypatch.setattr(engine, "_suggest_parallelism", lambda _configured: budget["slots"])
    gate = engine.AdaptiveGate(2)
    await gate.__aenter__()
    budget["slots"] = 1
    acquired = asyncio.Event()

    async def wait_for_slot() -> None:
        await gate.__aenter__()
        acquired.set()

    waiting = asyncio.create_task(wait_for_slot())
    await asyncio.sleep(0)
    assert not acquired.is_set()
    await gate.__aexit__(None, None, None)
    await asyncio.wait_for(waiting, timeout=0.2)
    assert acquired.is_set()
    await gate.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_interrupted_running_item_is_requeued_and_processed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "note.md").write_text("note", encoding="utf-8")
    state = tmp_path / "state"
    store = JobStore(state)
    run_id = store.create_run("classify", workspace, "test-model", [("note.md", "text")])
    store.set_item(run_id, "note.md", "running")
    monkeypatch.setattr(engine, "_suggest_parallelism", lambda _configured: 1)
    provider = DelayedProvider()

    resumed_id, _ = await run_batch("", workspace, state, run_id=run_id, provider=provider)

    assert resumed_id == run_id
    assert provider.calls == ["note.md"]
    assert store.counts(run_id) == {"complete": 1}


@pytest.mark.asyncio
async def test_resume_marks_deleted_input_failed_without_calling_provider(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    missing = workspace / "gone.md"
    missing.write_text("note", encoding="utf-8")
    state = tmp_path / "state"
    store = JobStore(state)
    run_id = store.create_run("classify", workspace, "test-model", [("gone.md", "text")])
    missing.unlink()
    provider = DelayedProvider()

    resumed_id, report = await run_batch("", workspace, state, run_id=run_id, provider=provider)

    assert resumed_id == run_id
    assert provider.calls == []
    assert store.counts(run_id) == {"failed": 1}
    assert "File no longer exists or is no longer supported" in report.read_text(encoding="utf-8")
