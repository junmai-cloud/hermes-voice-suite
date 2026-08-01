"""Orchestration for implementation routing and independent audits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .technical_ledger import TechnicalLedger
from .technical_ops import (
    AuditPacket,
    AuditVerdict,
    CodexWorker,
    OperationKind,
    TaskState,
    TechnicalTask,
    WorkerUnavailable,
)


@dataclass(frozen=True)
class DispatchResult:
    task_id: str
    worker_id: str
    job_id: str


class TechnicalOrchestrator:
    """Route implementation to local Codex when ready and always audit on VPS."""

    def __init__(
        self,
        ledger: TechnicalLedger,
        *,
        vps_worker: CodexWorker,
        local_worker: CodexWorker | None = None,
        auditor_worker: CodexWorker | None = None,
    ) -> None:
        self.ledger = ledger
        self.vps_worker = vps_worker
        self.local_worker = local_worker
        self.auditor_worker = auditor_worker or vps_worker

    def register(
        self,
        summary: str,
        operation: OperationKind | str,
        repo_path: str,
        *,
        branch: str | None = None,
        rollback_plan: str = "Revert the task branch before deployment.",
    ) -> TechnicalTask:
        task = TechnicalTask(
            summary=summary,
            operation=operation,
            repo_path=repo_path,
            branch=branch,
            rollback_plan=rollback_plan,
        )
        self.ledger.create(task)
        self.ledger.transition(task.task_id, TaskState.PLANNED)
        return TechnicalTask.from_dict(self._record(task.task_id))

    def dispatch(self, task_id: str, prompt: str, *, prefer_local: bool = True) -> DispatchResult:
        record = self._record(task_id)
        if record["state"] not in {TaskState.PLANNED.value, TaskState.NEEDS_FIX.value}:
            raise ValueError(f"task must be PLANNED or NEEDS_FIX before dispatch, got {record['state']}")
        task = TechnicalTask.from_dict(record)
        if task.audit_required and not task.branch:
            raise ValueError("audited technical work requires a Git branch or worktree")
        if task.requires_confirmation and not record["user_confirmed"]:
            raise ValueError("explicit user confirmation is required before this operation")
        if record["state"] == TaskState.NEEDS_FIX.value and not record["user_confirmed"]:
            raise ValueError("user confirmation is required before applying the audit improvement plan")
        worker = self._select_worker(prefer_local=prefer_local)
        self.ledger.assign_worker(task_id, worker.worker_id)
        self.ledger.transition(task_id, TaskState.IMPLEMENTING)
        try:
            job_id = worker.submit(task, prompt)
        except Exception:
            self.ledger.transition(task_id, TaskState.BLOCKED)
            raise
        self.ledger.assign_worker(task_id, worker.worker_id, job_id)
        return DispatchResult(task_id, worker.worker_id, job_id)

    def record_result(self, task_id: str, packet: AuditPacket) -> None:
        if task_id != packet.task_id:
            raise ValueError("audit packet task_id does not match task")
        self.ledger.record_packet(packet)

    def submit_audit(self, task_id: str, packet: AuditPacket, prompt: str) -> DispatchResult:
        """Store evidence and submit an independent Codex review job."""

        if task_id != packet.task_id:
            raise ValueError("audit packet task_id does not match task")
        self.ledger.record_packet(packet)
        auditor = self.auditor_worker
        if not auditor.status().ready:
            self.ledger.transition(task_id, TaskState.BLOCKED)
            raise WorkerUnavailable("VPS Codex auditor is not ready")
        task = TechnicalTask.from_dict(self._record(task_id))
        try:
            job_id = auditor.submit(task, prompt)
        except Exception:
            self.ledger.transition(task_id, TaskState.BLOCKED)
            raise
        self.ledger.assign_auditor(task_id, auditor.worker_id, job_id)
        return DispatchResult(task_id, auditor.worker_id, job_id)

    def complete_audit(self, task_id: str, raw_result: str) -> AuditVerdict:
        """Accept a strict JSON verdict and advance the task only on valid evidence."""

        verdict = AuditVerdict.from_json(raw_result)
        self.ledger.record_verdict(task_id, verdict)
        return verdict

    def audit(self, task_id: str, verdict: AuditVerdict) -> None:
        self.ledger.record_verdict(task_id, verdict)

    def mark_deployed(self, task_id: str) -> None:
        record = self._record(task_id)
        if record["requires_confirmation"] and not record["user_confirmed"]:
            raise ValueError("explicit user confirmation is required before deployment")
        self.ledger.transition(task_id, TaskState.DEPLOYED)

    def confirm(self, task_id: str) -> None:
        self.ledger.confirm(task_id)

    def can_report_complete(self, task_id: str) -> bool:
        return self.ledger.can_report_complete(task_id)

    def _select_worker(self, *, prefer_local: bool) -> CodexWorker:
        if prefer_local and self.local_worker is not None and self.local_worker.status().ready:
            return self.local_worker
        if self.vps_worker.status().ready:
            return self.vps_worker
        raise WorkerUnavailable("no Codex implementation worker is ready")

    def _record(self, task_id: str) -> dict[str, Any]:
        record = self.ledger.get(task_id)
        if record is None:
            raise KeyError(f"unknown technical task: {task_id}")
        return record
