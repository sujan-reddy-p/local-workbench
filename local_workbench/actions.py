"""Explicit, non-destructive application of reviewed category suggestions."""

from __future__ import annotations

import re
import shutil
from pathlib import Path, PurePosixPath

from .store import JobStore


def apply_category_copies(state_dir: Path, run_id: int) -> tuple[Path, int]:
    store = JobStore(state_dir)
    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"Run {run_id} does not exist")
    if run["status"] not in {"complete", "needs-attention"}:
        raise ValueError("Only finished runs can be applied")
    root = Path(str(run["workspace"])).resolve(strict=True)
    output = state_dir.expanduser().resolve() / "exports" / f"run-{run_id}"
    output.mkdir(parents=True, exist_ok=True)
    copied = 0
    for row in store.results(run_id):
        result = row.get("result")
        if row["status"] != "complete" or not result:
            continue
        relative = PurePosixPath(str(row["relative_path"]))
        if relative.is_absolute() or ".." in relative.parts:
            continue
        source = root.joinpath(*relative.parts)
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(root):
            continue
        category = re.sub(r"[^A-Za-z0-9_]+", "_", str(result.get("category", "uncategorized"))).strip("_")[:64]
        category = category or "uncategorized"
        destination = output / category / Path(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            continue
        shutil.copy2(source, destination)
        copied += 1
    return output, copied
