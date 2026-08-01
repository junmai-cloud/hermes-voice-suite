"""Privacy-safe SQLite ledger for technical tasks and audit evidence."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from .technical_ops import AuditPacket, AuditVerdict, TaskState, TechnicalTask, utc_now


_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\b(?:sk|ghp|xoxb|xoxp)-[A-Za-z0-9._-]{12,}\b"),
)


def redact_text(value: str) -> str:
    """Remove common credentials before text enters the technical ledger."""

    def replacement(match: re.Match[str]) -> str:
        raw = match.group(0)
        if raw.lower().startswith("bearer "):
            return "Bearer <REDACTED>"
        if ":" in raw:
            return f"{raw.split(':', 1)[0]}: <REDACTED>"
        if "=" in raw:
            return f"{raw.split('=', 1)[0]}=<REDACTED>"
        return "<REDACTED>"

    result = str(value)
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {str(key): _redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


_ALLOWED_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.REQUESTED: {TaskState.PLANNED, TaskState.CANCELLED},
    TaskState.PLANNED: {TaskState.IMPLEMENTING, TaskState.CANCELLED},
    TaskState.IMPLEMENTING: {
        TaskState.VERIFYING,
        TaskState.NEEDS_FIX,
        TaskState.BLOCKED,
        TaskState.CANCELLED,
    },
    TaskState.VERIFYING: {TaskState.APPROVED, TaskState.NEEDS_FIX, TaskState.BLOCKED},
    TaskState.NEEDS_FIX: {TaskState.IMPLEMENTING, TaskState.CANCELLED},
    TaskState.BLOCKED: {TaskState.PLANNED, TaskState.CANCELLED},
    TaskState.APPROVED: {TaskState.DEPLOYED, TaskState.CANCELLED},
    TaskState.DEPLOYED: set(),
    TaskState.CANCELLED: set(),
}


class TechnicalLedger:
    """Persist task state without storing audio or transcript content."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
            path = hermes_home / "voice-suite" / "technical.db"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS technical_tasks (
                    task_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    repo_path TEXT NOT NULL,
                    branch TEXT,
                    rollback_plan TEXT NOT NULL,
                    state TEXT NOT NULL,
                    implementer TEXT,
                    worker_job_id TEXT,
                    auditor TEXT,
                    audit_job_id TEXT,
                    requires_confirmation INTEGER NOT NULL,
                    user_confirmed INTEGER NOT NULL DEFAULT 0,
                    packet_json TEXT,
                    verdict_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column(connection, "auditor", "TEXT")
            self._ensure_column(connection, "audit_job_id", "TEXT")
            self._ensure_column(connection, "user_confirmed", "INTEGER NOT NULL DEFAULT 0")
            connection.commit()

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, name: str, definition: str) -> None:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(technical_tasks)")}
        if name not in columns:
            connection.execute(f"ALTER TABLE technical_tasks ADD COLUMN {name} {definition}")

    def create(self, task: TechnicalTask) -> TechnicalTask:
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO technical_tasks
                (task_id, summary, operation, repo_path, branch, rollback_plan,
                 state, implementer, worker_job_id, auditor, audit_job_id, requires_confirmation, user_confirmed,
                 packet_json, verdict_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, NULL, NULL, ?, ?)
                """,
                (
                    task.task_id,
                    redact_text(task.summary),
                    task.operation.value,
                    redact_text(task.repo_path),
                    redact_text(task.branch or "") or None,
                    redact_text(task.rollback_plan),
                    task.state.value,
                    task.implementer,
                    int(bool(task.requires_confirmation)),
                    int(bool(task.user_confirmed)),
                    task.created_at,
                    now,
                ),
            )
            connection.commit()
        return task

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM technical_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list(self, *, state: TaskState | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM technical_tasks"
        params: tuple[Any, ...] = ()
        if state is not None:
            query += " WHERE state = ?"
            params = (state.value,)
        query += " ORDER BY created_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def assign_worker(self, task_id: str, worker_id: str, job_id: str | None = None) -> None:
        self._require(task_id)
        with self._connect() as connection:
            connection.execute(
                "UPDATE technical_tasks SET implementer = ?, worker_job_id = ?, updated_at = ? WHERE task_id = ?",
                (worker_id, job_id, utc_now(), task_id),
            )
            connection.commit()

    def assign_auditor(self, task_id: str, worker_id: str, job_id: str | None = None) -> None:
        self._require(task_id)
        with self._connect() as connection:
            connection.execute(
                "UPDATE technical_tasks SET auditor = ?, audit_job_id = ?, updated_at = ? WHERE task_id = ?",
                (worker_id, job_id, utc_now(), task_id),
            )
            connection.commit()

    def confirm(self, task_id: str) -> None:
        """Record the user's explicit approval for a sensitive operation."""

        self._require(task_id)
        with self._connect() as connection:
            connection.execute(
                "UPDATE technical_tasks SET user_confirmed = 1, updated_at = ? WHERE task_id = ?",
                (utc_now(), task_id),
            )
            connection.commit()

    def transition(self, task_id: str, target: TaskState) -> None:
        record = self._require(task_id)
        current = self._current_state(task_id)
        if target is TaskState.APPROVED:
            if current is not TaskState.VERIFYING:
                raise ValueError(f"invalid task transition {current.value} -> {target.value}")
            raise ValueError("APPROVED can only be reached through a Codex audit verdict")
        if target is TaskState.DEPLOYED and not record["verdict_json"]:
            raise ValueError("DEPLOYED requires a recorded Codex audit verdict")
        if target not in _ALLOWED_TRANSITIONS[current]:
            raise ValueError(f"invalid task transition {current.value} -> {target.value}")
        with self._connect() as connection:
            connection.execute(
                "UPDATE technical_tasks SET state = ?, updated_at = ? WHERE task_id = ?",
                (target.value, utc_now(), task_id),
            )
            connection.commit()

    def record_packet(self, packet: AuditPacket) -> None:
        current = self._current_state(packet.task_id)
        if current not in {TaskState.IMPLEMENTING, TaskState.NEEDS_FIX}:
            raise ValueError(f"cannot record audit packet while task is {current.value}")
        payload = _redact(packet.to_dict())
        with self._connect() as connection:
            connection.execute(
                "UPDATE technical_tasks SET state = ?, packet_json = ?, updated_at = ? WHERE task_id = ?",
                (TaskState.VERIFYING.value, json.dumps(payload, ensure_ascii=False), utc_now(), packet.task_id),
            )
            connection.commit()

    def record_verdict(self, task_id: str, verdict: AuditVerdict) -> None:
        record = self._require(task_id)
        if not record["packet_json"]:
            raise ValueError("cannot record audit verdict without an audit packet")
        if record["state"] != TaskState.VERIFYING.value:
            raise ValueError(f"cannot record audit verdict while task is {record['state']}")
        target = TaskState.APPROVED if verdict.passed else (
            TaskState.NEEDS_FIX if verdict.status.value == "FAIL" else TaskState.BLOCKED
        )
        payload = _redact(verdict.to_dict())
        with self._connect() as connection:
            connection.execute(
                "UPDATE technical_tasks SET state = ?, verdict_json = ?, updated_at = ? WHERE task_id = ?",
                (target.value, json.dumps(payload, ensure_ascii=False), utc_now(), task_id),
            )
            connection.commit()

    def can_report_complete(self, task_id: str) -> bool:
        record = self._require(task_id)
        return bool(record["verdict_json"]) and record["state"] in {
            TaskState.APPROVED.value,
            TaskState.DEPLOYED.value,
        }

    def _current_state(self, task_id: str) -> TaskState:
        record = self._require(task_id)
        return TaskState(record["state"])

    def _require(self, task_id: str) -> dict[str, Any]:
        record = self.get(task_id)
        if record is None:
            raise KeyError(f"unknown technical task: {task_id}")
        return record

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        for key in ("packet_json", "verdict_json"):
            if result[key]:
                result[key] = json.loads(result[key])
        result["requires_confirmation"] = bool(result["requires_confirmation"])
        result["user_confirmed"] = bool(result["user_confirmed"])
        return result
