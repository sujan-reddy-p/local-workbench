"""Textual interface for submitting and supervising local batch work."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Static,
)

from .actions import apply_category_copies
from .engine import available_parallelism, run_batch


class ApprovalScreen(ModalScreen[bool]):
    CSS = """
    ApprovalScreen { align: center middle; }
    #approval-box { width: 64; height: 11; border: round $warning; background: $surface; padding: 1 2; }
    #approval-buttons { height: 3; align-horizontal: center; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="approval-box"):
            yield Label("Copy categorized files into a new export folder? Originals will remain untouched.")
            with Horizontal(id="approval-buttons"):
                yield Button("Copy files", id="approve", variant="warning")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "approve")


class WorkbenchApp(App[None]):
    TITLE = "Local Workbench"
    SUB_TITLE = "Local-first batch work"
    CSS = """
    Screen { padding: 1 2; }
    #instructions { height: 3; color: $text-muted; }
    #goal { margin: 1 0; }
    #workspace { margin: 0 0 1 0; }
    #controls { height: 3; }
    #progress { margin: 1 0; }
    #log { height: 1fr; border: round $primary; }
    """

    def __init__(self, workspace: Path, state_dir: Path, model: str = "gemma3:4b", max_parallel: int = 2) -> None:
        super().__init__()
        self.workspace = workspace
        self.state_dir = state_dir
        self.model = model
        self.max_parallel = max_parallel
        self.busy = False
        self.last_run_id: int | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Static("Describe a batch task. The model analyzes files locally; nothing changes until you approve copies.", id="instructions")
            yield Input(placeholder="e.g. Group these support notes by issue and summarize each group", id="goal")
            yield Static(f"Workspace: {self.workspace}", id="workspace")
            yield Static(f"Ollama model: {self.model} · adaptive request cap: {available_parallelism(self.max_parallel)}", id="limits")
            with Horizontal(id="controls"):
                yield Button("Start local run", id="start", variant="primary")
                yield Button("Review and copy categories", id="apply", disabled=True, variant="warning")
            yield ProgressBar(total=100, show_eta=False, id="progress")
            yield RichLog(markup=False, wrap=True, id="log")
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "apply":
            if self.last_run_id is None or self.busy:
                return
            approved = await self.push_screen_wait(ApprovalScreen())
            if approved:
                try:
                    output, copied = apply_category_copies(self.state_dir, self.last_run_id)
                    self.query_one("#log", RichLog).write(f"Copied {copied} reviewed files to {output}; originals unchanged.")
                except Exception as exc:  # noqa: BLE001 - surface apply failures in the UI
                    self.query_one("#log", RichLog).write(f"Copy action failed: {exc}")
            return
        if event.button.id != "start" or self.busy:
            return
        goal = self.query_one("#goal", Input).value.strip()
        if not goal:
            self.query_one("#log", RichLog).write("Enter a task first.")
            return
        self.busy = True
        event.button.disabled = True
        self.query_one("#apply", Button).disabled = True
        self.query_one("#log", RichLog).write("Scanning supported files and creating a durable run…")
        progress = self.query_one("#progress", ProgressBar)

        def on_progress(done: int, total: int, path: str) -> None:
            progress.update(total=total, progress=done)
            self.query_one("#log", RichLog).write(f"{done}/{total} · {path}")

        try:
            run_id, report = await run_batch(
                goal, self.workspace, self.state_dir, self.model, self.max_parallel, progress=on_progress
            )
            self.last_run_id = run_id
            self.query_one("#log", RichLog).write(f"Run {run_id} finished. Report: {report}")
            self.query_one("#apply", Button).disabled = False
        except Exception as exc:  # noqa: BLE001 - surface run failures in the UI
            self.query_one("#log", RichLog).write(f"Run failed: {exc}")
        finally:
            self.busy = False
            event.button.disabled = False


def run_tui(workspace: Path, state_dir: Path, model: str, max_parallel: int) -> None:
    WorkbenchApp(workspace, state_dir, model, max_parallel).run()


