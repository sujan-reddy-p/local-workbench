"""Textual interface for submitting and supervising local batch work."""

from __future__ import annotations

from pathlib import Path

from textual import work
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
    TextArea,
)

from .actions import apply_category_copies
from .engine import available_parallelism, run_batch
from .store import JobStore


class ApprovalScreen(ModalScreen[bool]):
    CSS = """
    ApprovalScreen { align: center middle; }
    #approval-box { width: 96%; height: 96%; border: round $warning; background: $surface; padding: 1 2; }
    #review-heading { width: 1fr; height: auto; }
    #review-report { height: 1fr; min-height: 5; border: round $primary; }
    #approval-buttons { height: 4; align-horizontal: center; }
    #approval-buttons Button { min-width: 18; }
    """

    def __init__(self, report: str, copy_count: int, failed_count: int = 0) -> None:
        super().__init__()
        self.report = report
        self.copy_count = copy_count
        self.failed_count = failed_count

    def compose(self) -> ComposeResult:
        with Vertical(id="approval-box"):
            yield Label(
                f"Review this read-only report before copying. Completed: {self.copy_count}; "
                f"failed: {self.failed_count}. Suggestions may be wrong; scanner-excluded files "
                "are not listed.",
                id="review-heading",
            )
            yield TextArea(self.report, read_only=True, show_line_numbers=False, id="review-report")
            with Horizontal(id="approval-buttons"):
                yield Button(
                    f"Copy {self.copy_count} completed files",
                    id="approve",
                    variant="warning",
                    disabled=self.copy_count == 0,
                )
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
        self.last_report: Path | None = None
        self.last_copy_count = 0
        self.last_failed_count = 0
        self.reviewing = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Static("Describe a per-file task. Review the generated report before approving copies.", id="instructions")
            yield Input(placeholder="e.g. Tag each note by issue and summarize that file", id="goal")
            yield Static(f"Workspace: {self.workspace}", id="workspace")
            yield Static(f"Ollama model: {self.model} · adaptive request cap: {available_parallelism(self.max_parallel)}", id="limits")
            with Horizontal(id="controls"):
                yield Button("Start local run", id="start", variant="primary")
                yield Button("Review report / copy files", id="apply", disabled=True, variant="warning")
            yield ProgressBar(total=100, show_eta=False, id="progress")
            yield RichLog(markup=False, wrap=True, id="log")
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "apply":
            if self.last_run_id is None or self.last_report is None or self.busy or self.reviewing:
                return
            run_id = self.last_run_id
            try:
                report_text = self.last_report.read_text(encoding="utf-8")
            except OSError as exc:
                self.query_one("#log", RichLog).write(f"Cannot read run report {self.last_report}: {exc}")
                return
            self.reviewing = True
            apply_button = self.query_one("#apply", Button)
            start_button = self.query_one("#start", Button)
            apply_button.disabled = True
            start_button.disabled = True
            self._review_and_apply(report_text, run_id, start_button, apply_button)
            return
        if event.button.id != "start" or self.busy or self.reviewing:
            return
        goal = self.query_one("#goal", Input).value.strip()
        if not goal:
            self.query_one("#log", RichLog).write("Enter a task first.")
            return
        self.busy = True
        self.last_run_id = None
        self.last_report = None
        self.last_copy_count = 0
        self.last_failed_count = 0
        event.button.disabled = True
        self.query_one("#apply", Button).disabled = True
        progress = self.query_one("#progress", ProgressBar)
        progress.update(total=100, progress=0)
        self.query_one("#log", RichLog).clear()
        self.query_one("#log", RichLog).write("Scanning supported files and creating a durable run…")

        def on_progress(done: int, total: int, path: str) -> None:
            progress.update(total=total, progress=done)
            self.query_one("#log", RichLog).write(f"{done}/{total} · {path}")

        try:
            run_id, report = await run_batch(
                goal, self.workspace, self.state_dir, self.model, self.max_parallel, progress=on_progress
            )
            self.last_run_id = run_id
            self.last_report = report
            counts = JobStore(self.state_dir).counts(run_id)
            self.last_copy_count = counts.get("complete", 0)
            self.last_failed_count = counts.get("failed", 0)
            self.query_one("#log", RichLog).write(
                f"Run {run_id} finished: {self.last_copy_count} complete, {self.last_failed_count} failed."
            )
            self.query_one("#log", RichLog).write(f"Report: {report}")
            self.query_one("#log", RichLog).write(
                "Hidden, unsupported, oversized, and non-regular files are skipped before processing and are not listed."
            )
            self.query_one("#apply", Button).disabled = False
        except Exception as exc:  # noqa: BLE001 - surface run failures in the UI
            self.query_one("#log", RichLog).write(f"Run failed: {exc}")
        finally:
            self.busy = False
            event.button.disabled = False

    @work
    async def _review_and_apply(
        self, report_text: str, run_id: int, start_button: Button, apply_button: Button
    ) -> None:
        try:
            approved = await self.push_screen_wait(
                ApprovalScreen(report_text, self.last_copy_count, self.last_failed_count)
            )
            if approved:
                try:
                    output, copied = apply_category_copies(self.state_dir, run_id)
                    self.query_one("#log", RichLog).write(f"Copied {copied} reviewed files to {output}; originals unchanged.")
                except Exception as exc:  # noqa: BLE001 - surface apply failures in the UI
                    self.query_one("#log", RichLog).write(f"Copy action failed: {exc}")
        finally:
            self.reviewing = False
            start_button.disabled = False
            apply_button.disabled = self.last_report is None


def run_tui(workspace: Path, state_dir: Path, model: str, max_parallel: int) -> None:
    WorkbenchApp(workspace, state_dir, model, max_parallel).run()


