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
    parser.add_argument("--parallel", type=int, default=2, help="Maximum concurrent inference requests (1-4; default 2)")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--task", help="Run one batch task without opening the TUI")
    operation.add_argument("--resume", type=int, help="Resume pending/failed items for a run ID")
    parser.add_argument("--check", action="store_true", help="Check that Ollama is reachable and the model is installed")
    return parser


def main() -> None:
    args = build_parser().parse_args()
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
    if args.task or args.resume is not None:
        async def execute() -> None:
            run_id, report = await run_batch(
                args.task or "", args.workspace, args.state_dir, args.model, args.parallel, args.resume
            )
            print(f"Run {run_id} complete. Report: {report}")
        asyncio.run(execute())
    else:
        run_tui(args.workspace, args.state_dir, args.model, args.parallel)
