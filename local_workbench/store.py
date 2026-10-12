"""SQLite persistence for resumable runs and per-file work states."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def _now() -> str:
    return datetime.now(UTC).isoformat()


class JobStore:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir.expanduser().resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_dir / "jobs.sqlite3"
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal TEXT NOT NULL,
                    workspace TEXT NOT NULL,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS items (
                    run_id INTEGER NOT NULL REFERENCES runs(id),
                    relative_path TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, relative_path)
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def create_run(self, goal: str, workspace: Path, model: str, items: list[tuple[str, str]]) -> int:
        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO runs(goal,workspace,model,status,created_at) VALUES(?,?,?,?,?)",
                (goal, str(workspace), model, "queued", _now()),
            )
            run_id = int(cursor.lastrowid)
            db.executemany(
                "INSERT INTO items(run_id,relative_path,kind,status,updated_at) VALUES(?,?,?,?,?)",
                [(run_id, path, kind, "queued", _now()) for path, kind in items],
            )
        return run_id

    def get_run(self, run_id: int) -> dict[str, object] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            return dict(row) if row else None

    def pending_items(self, run_id: int) -> list[dict[str, object]]:
        with self._connect() as db:
            db.execute("UPDATE items SET status='queued',updated_at=? WHERE run_id=? AND status='running'", (_now(), run_id))
            return [dict(row) for row in db.execute(
                "SELECT * FROM items WHERE run_id=? AND status IN ('queued','failed') ORDER BY relative_path",
                (run_id,),
            )]

    def set_run_status(self, run_id: int, status: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE runs SET status=? WHERE id=?", (status, run_id))

    def set_item(self, run_id: int, path: str, status: str, result: dict[str, object] | None = None, error: str | None = None) -> None:
        encoded = json.dumps(result, ensure_ascii=False) if result is not None else None
        with self._connect() as db:
            db.execute(
                "UPDATE items SET status=?,result_json=?,error=?,updated_at=? WHERE run_id=? AND relative_path=?",
                (status, encoded, error, _now(), run_id, path),
            )

    def counts(self, run_id: int) -> dict[str, int]:
        with self._connect() as db:
            rows = db.execute("SELECT status,COUNT(*) AS count FROM items WHERE run_id=? GROUP BY status", (run_id,))
            return {str(row["status"]): int(row["count"]) for row in rows}

    def results(self, run_id: int) -> list[dict[str, object]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM items WHERE run_id=? ORDER BY relative_path", (run_id,)).fetchall()
        return [
            {**dict(row), "result": json.loads(row["result_json"]) if row["result_json"] else None}
            for row in rows
        ]
