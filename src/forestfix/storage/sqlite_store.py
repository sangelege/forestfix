"""SQLite persistence for tasks, candidates, and verification reports."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from forestfix.domain.task_spec import TaskSpec


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    spec_json TEXT NOT NULL,
                    baseline_json TEXT,
                    report_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column(connection, "tasks", "baseline_json", "TEXT")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS candidates (
                    candidate_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    patch TEXT NOT NULL DEFAULT '',
                    report_json TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_candidates_task_id "
                "ON candidates(task_id)"
            )

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        sql_type: str,
    ) -> None:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")

    def create_task(self, spec: TaskSpec) -> None:
        now = datetime.now(UTC).isoformat()
        spec_json = json.dumps(spec.model_dump(mode="json"), ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks(
                    task_id, status, spec_json, baseline_json, report_json, created_at, updated_at
                )
                VALUES (?, ?, ?, NULL, NULL, ?, ?)
                """,
                (spec.task_id, "created", spec_json, now, now),
            )

    def save_baseline(self, task_id: str, report: dict[str, Any]) -> None:
        now = datetime.now(UTC).isoformat()
        report_json = json.dumps(report, ensure_ascii=False)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks
                SET baseline_json = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (report_json, now, task_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"task not found: {task_id}")

    def save_report(self, task_id: str, report: dict[str, Any]) -> None:
        status = "completed" if report.get("accepted") is True else "failed"
        now = datetime.now(UTC).isoformat()
        report_json = json.dumps(report, ensure_ascii=False)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks
                SET status = ?, report_json = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (status, report_json, now, task_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"task not found: {task_id}")

    def update_task_status(self, task_id: str, status: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
                (status, now, task_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"task not found: {task_id}")

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT task_id, status, spec_json, baseline_json, report_json, "
                "created_at, updated_at "
                "FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_tasks(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT task_id, status, spec_json, baseline_json, report_json, "
                "created_at, updated_at FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_candidate(
        self,
        *,
        candidate_id: str,
        task_id: str,
        provider: str,
        summary: str,
        patch: str,
        status: str,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO candidates(
                    candidate_id, task_id, provider, summary, patch,
                    report_json, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (candidate_id, task_id, provider, summary, patch, status, now, now),
            )

    def update_candidate(
        self,
        candidate_id: str,
        *,
        status: str | None = None,
        summary: str | None = None,
        patch: str | None = None,
        report: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        current = self.get_candidate(candidate_id)
        if current is None:
            raise KeyError(f"candidate not found: {candidate_id}")
        new_status = status if status is not None else current["status"]
        new_summary = summary if summary is not None else current["summary"]
        new_patch = patch if patch is not None else current["patch"]
        new_report = report if report is not None else current["report"]
        report_json = (
            json.dumps(new_report, ensure_ascii=False) if new_report is not None else None
        )
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE candidates
                SET status = ?, summary = ?, patch = ?, report_json = ?, updated_at = ?
                WHERE candidate_id = ?
                """,
                (new_status, new_summary, new_patch, report_json, now, candidate_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"candidate not found: {candidate_id}")

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT candidate_id, task_id, provider, summary, patch, report_json, "
                "status, created_at, updated_at FROM candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["report"] = (
            json.loads(result.pop("report_json")) if result.get("report_json") else None
        )
        return result

    def list_candidates(self, task_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT candidate_id, task_id, provider, summary, patch, report_json, "
                "status, created_at, updated_at FROM candidates "
                "WHERE task_id = ? ORDER BY created_at ASC",
                (task_id,),
            ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            record["report"] = (
                json.loads(record.pop("report_json"))
                if record.get("report_json")
                else None
            )
            results.append(record)
        return results
