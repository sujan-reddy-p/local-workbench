"""CLI entry point. Launches the TUI by default, or runs a task directly."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .engine import run_batch
from .ollama import OllamaClient
from .tui import run_tui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run safe, resumable batch analysis with a local Ollama model")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="Folder to inspect (default: current directory)")
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".local" / "share" / "local-workbench")
    parser.add_argument("--model", default="gemma3:4b", help="Ollama model (default: gemma3:4b)")
    parser.add_argument("--parallel", type=_parallel_count, default=2, help="Maximum concurrent inference requests (1-4; default 2)")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--task", help="Run one batch task without opening the TUI")
    operation.add_argument("--resume", type=int, help="Resume pending/failed items for a run ID")
    parser.add_argument("--check", action="store_true", help="Check that Ollama is reachable and the model is installed")
    return parser


def _parallel_count(value: str) -> int:
    """Parse the deliberately small concurrency range with an argparse error."""
    try:
        count = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer from 1 to 4") from exc
    if not 1 <= count <= 4:
        raise argparse.ArgumentTypeError("must be between 1 and 4")
    return count


def _validate_workspace(parser: argparse.ArgumentParser, workspace: Path) -> None:
    workspace = workspace.expanduser()
    if not workspace.exists():
        parser.error(f"--workspace does not exist: {workspace}")
    if not workspace.is_dir():
        parser.error(f"--workspace is not a directory: {workspace}")


def _run_summary(state_dir: Path, run_id: int) -> tuple[str, dict[str, int]]:
    from .store import JobStore

    store = JobStore(state_dir)
    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"Run {run_id} does not exist")
    return str(run["status"]), store.counts(run_id)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.task is not None and not args.task.strip():
        parser.error("--task must not be empty")
    if args.task is not None or args.resume is not None:
        _validate_workspace(parser, args.workspace)
    if args.check:
        try:
            import json
            import urllib.request

            client = OllamaClient(args.model)
            with urllib.request.urlopen(client.host + "/api/tags", timeout=5) as response:
                models = json.loads(response.read())
            installed = [item.get("name", "") for item in models.get("models", [])]
            if args.model not in installed:
                raise SystemExit(f"Model {args.model!r} is not installed. Run: ollama pull {args.model}")
            print(f"Ollama is ready at {client.host}; {args.model} is installed.")
        except SystemExit:
            raise
        except Exception as exc:
            raise SystemExit(f"Ollama check failed: {exc}") from exc
        return
    if args.task is not None or args.resume is not None:
        async def execute() -> None:
            try:
                run_id, report = await run_batch(
                    args.task or "", args.workspace, args.state_dir, args.model, args.parallel, args.resume
                )
                status, counts = _run_summary(args.state_dir, run_id)
            except (OSError, ValueError) as exc:
                raise SystemExit(f"Error: {exc}") from exc
            total = sum(counts.values())
            complete = counts.get("complete", 0)
            failed = counts.get("failed", 0)
            if status == "needs-attention" or failed:
                print(
                    f"Run {run_id} needs attention ({complete}/{total} complete, {failed} failed). "
                    f"Report: {report}"
                )
                raise SystemExit(1)
            print(f"Run {run_id} complete ({complete}/{total} complete). Report: {report}")
        asyncio.run(execute())
    else:
        _validate_workspace(parser, args.workspace)
        run_tui(args.workspace, args.state_dir, args.model, args.parallel)
