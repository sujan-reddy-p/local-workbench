from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import Button, TextArea

from local_workbench import tui
from local_workbench.tui import ApprovalScreen, WorkbenchApp


@pytest.mark.asyncio
async def test_report_is_shown_before_copy_requires_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_dir = tmp_path / "state"
    report_path = tmp_path / "run-1.md"
    report = "# Run 1\n\n## notes.md\n\n**Category:** Follow-up\n"
    report_path.write_text(report, encoding="utf-8")
    copied: list[tuple[Path, int]] = []

    def fake_copy(state_dir: Path, run_id: int) -> tuple[Path, int]:
        copied.append((state_dir, run_id))
        return tmp_path / "exports", 1

    monkeypatch.setattr(tui, "apply_category_copies", fake_copy)
    app = WorkbenchApp(tmp_path, state_dir)
    app.last_run_id = 1
    app.last_report = report_path
    app.last_copy_count = 1

    async with app.run_test() as pilot:
        app.query_one("#apply", Button).disabled = False
        await pilot.click("#apply")
        await pilot.pause()

        assert isinstance(app.screen, ApprovalScreen)
        assert app.screen.query_one("#review-report", TextArea).text == report
        assert copied == []

        await pilot.click("#cancel")
        await pilot.pause()
        assert copied == []

        await pilot.click("#apply")
        await pilot.pause()
        await pilot.click("#approve")
        await pilot.pause()
        assert copied == [(state_dir, 1)]


@pytest.mark.asyncio
async def test_zero_complete_review_disables_copy_and_cancel_restores_controls(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    report_path = tmp_path / "run-2.md"
    report_path.write_text("# Run 2\n\nNo files completed.\n", encoding="utf-8")
    app = WorkbenchApp(tmp_path, state_dir)
    app.last_run_id = 2
    app.last_report = report_path
    app.last_copy_count = 0

    async with app.run_test() as pilot:
        app.query_one("#apply", Button).disabled = False
        await pilot.click("#apply")
        await pilot.pause()

        assert isinstance(app.screen, ApprovalScreen)
        assert app.screen.query_one("#approve", Button).disabled

        await pilot.click("#approve")
        await pilot.pause()
        assert isinstance(app.screen, ApprovalScreen)

        await pilot.click("#cancel")
        await pilot.pause()
        assert not app.query_one("#start", Button).disabled
        assert not app.query_one("#apply", Button).disabled


@pytest.mark.asyncio
async def test_missing_report_is_logged_without_review_or_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    missing_report = tmp_path / "missing-run.md"
    copied: list[tuple[Path, int]] = []

    def fake_copy(state_dir: Path, run_id: int) -> tuple[Path, int]:
        copied.append((state_dir, run_id))
        return tmp_path / "exports", 1

    monkeypatch.setattr(tui, "apply_category_copies", fake_copy)
    app = WorkbenchApp(tmp_path, state_dir)
    app.last_run_id = 3
    app.last_report = missing_report
    app.last_copy_count = 1

    async with app.run_test() as pilot:
        app.query_one("#apply", Button).disabled = False
        await pilot.click("#apply")
        await pilot.pause()

        assert not isinstance(app.screen, ApprovalScreen)
        assert app.reviewing is False
        assert copied == []
        log_text = "".join(line.text for line in app.query_one("#log").lines)
        assert str(missing_report) in log_text


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(80, 24), (120, 36)])
async def test_review_layout_keeps_controls_reachable_at_terminal_sizes(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    workspace = Path("/") / ("workspace-" + "x" * 180)
    state_dir = tmp_path / "state"
    report_path = tmp_path / "run-4.md"
    report_path.write_text("# Run 4\n\n" + ("A readable report line.\n" * 4), encoding="utf-8")
    app = WorkbenchApp(workspace, state_dir)
    app.last_run_id = 4
    app.last_report = report_path
    app.last_copy_count = 1

    async with app.run_test(size=size) as pilot:
        start_button = app.query_one("#start", Button)
        apply_button = app.query_one("#apply", Button)
        apply_button.disabled = False
        await pilot.click("#apply")
        await pilot.pause()

        assert isinstance(app.screen, ApprovalScreen)
        report_area = app.screen.query_one("#review-report", TextArea)
        buttons = app.screen.query_one("#approval-buttons")
        assert report_area.region.height >= 5
        assert buttons.region.bottom <= size[1]
        for button in app.screen.query("#approval-buttons Button"):
            assert button.region.bottom <= size[1]

        await pilot.click("#cancel")
        await pilot.pause()
        assert not start_button.disabled
        assert not apply_button.disabled
