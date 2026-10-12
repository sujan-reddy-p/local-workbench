"""Bounded async execution, persistence, retry, and local report generation."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Self

from .ollama import OllamaClient
from .scanner import WorkItem, read_item, scan_workspace
from .store import JobStore


class AdaptiveGate:
    """Allow concurrent Ollama requests only when live system resources permit."""

    def __init__(self, user_cap: int) -> None:
        self.user_cap = user_cap
        self.active = 0
        self.condition = asyncio.Condition()

    async def __aenter__(self) -> Self:
        async with self.condition:
            while self.active >= _suggest_parallelism(self.user_cap):
                try:
                    await asyncio.wait_for(self.condition.wait(), timeout=1)
                except TimeoutError:
                    pass
            self.active += 1
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        async with self.condition:
            self.active -= 1
            self.condition.notify_all()


Progress = Callable[[int, int, str], None]


def _suggest_parallelism(configured: int, model_reserve_gb: float = 5.0) -> int:
    """Limit request concurrency by available memory and current CPU pressure."""
    try:
        import psutil
        available_gb = psutil.virtual_memory().available / (1024 ** 3)
        memory_cap = max(1, min(configured, int(max(1.0, (available_gb - 1.0) / model_reserve_gb))))
        if psutil.cpu_percent(interval=None) >= 85:
            return 1
        return memory_cap
    except (ImportError, OSError, AttributeError):
        return 1


async def run_batch(
    goal: str,
    workspace: Path,
    state_dir: Path,
    model: str = "gemma3:4b",
    max_parallel: int = 2,
    run_id: int | None = None,
    provider: OllamaClient | None = None,
    progress: Progress | None = None,
) -> tuple[int, Path]:
    if run_id is None and not goal.strip():
        raise ValueError("Describe the work to perform")
    if not 1 <= max_parallel <= 4:
        raise ValueError("max_parallel must be between 1 and 4")
    root = workspace.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"Workspace is not a directory: {root}")
    store = JobStore(state_dir)
    if run_id is None:
        discovered = scan_workspace(root)
        if not discovered:
            raise ValueError("No supported text or image files found in this workspace")
        run_id = store.create_run(goal, root, model, [(item.relative_path, item.kind) for item in discovered])
    else:
        run = store.get_run(run_id)
        if run is None:
            raise ValueError(f"Run {run_id} does not exist")
        if Path(str(run["workspace"])).resolve() != root:
            raise ValueError("Resume workspace must match the workspace recorded for this run")
        goal = str(run["goal"])
        model = str(run["model"])
    root_to_item: dict[str, WorkItem] = {item.relative_path: item for item in scan_workspace(root)}
    pending = store.pending_items(run_id)
    if not pending:
        store.set_run_status(run_id, "complete")
        report = write_report(store, run_id, state_dir)
        return run_id, report
    gate = AdaptiveGate(max_parallel)
    client = provider or OllamaClient(model=model)
    store.set_run_status(run_id, "running")
    completed_before = store.counts(run_id).get("complete", 0)
    total = len(store.results(run_id))
    done = completed_before

    async def process(row: dict[str, object]) -> None:
        nonlocal done
        relative_path = str(row["relative_path"])
        item = root_to_item.get(relative_path)
        if item is None:
            store.set_item(run_id, relative_path, "failed", error="File no longer exists or is no longer supported")
            done += 1
            if progress:
                progress(done, total, relative_path)
            return
        async with gate:
            store.set_item(run_id, relative_path, "running")
            try:
                content = read_item(item)
                result = await asyncio.to_thread(client.inspect, goal, relative_path, content)
                store.set_item(run_id, relative_path, "complete", result=result)
            except Exception as exc:  # noqa: BLE001 - isolate a failed file from sibling jobs
                store.set_item(run_id, relative_path, "failed", error=str(exc)[:1000])
            finally:
                done += 1
                if progress:
                    progress(done, total, relative_path)

    await asyncio.gather(*(process(row) for row in pending))
    counts = store.counts(run_id)
    store.set_run_status(run_id, "complete" if counts.get("failed", 0) == 0 else "needs-attention")
    report = write_report(store, run_id, state_dir)
    return run_id, report


def write_report(store: JobStore, run_id: int, state_dir: Path) -> Path:
    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"Run {run_id} does not exist")
    report_dir = state_dir.expanduser().resolve() / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"run-{run_id}.md"
    rows = store.results(run_id)
    lines = [
        f"# Local Workbench run {run_id}",
        "",
        f"**Task:** {run['goal']}",
        f"**Workspace:** `{run['workspace']}`",
        f"**Model:** `{run['model']}`",
        f"**Status:** {run['status']}",
        "",
        "This report contains model suggestions only. Input files were not modified.",
        "",
    ]
    for row in rows:
        lines.extend([f"## {row['relative_path']}", ""])
        result = row.get("result")
        if result:
            lines.extend([
                f"**Category:** {result['category']}  ",
                f"**Confidence:** {result['confidence']:.0%}  ",
                f"**Summary:** {result['summary']}",
            ])
            if result.get("notes"):
                lines.append(f"**Notes:** {result['notes']}")
        else:
            lines.append(f"**{row['status']}:** {row.get('error') or 'No result'}")
        lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def available_parallelism(configured: int = 2) -> int:
    return _suggest_parallelism(configured)
