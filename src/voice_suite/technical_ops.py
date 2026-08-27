"""Contracts for Hermes/Codex technical operations.

This module deliberately contains no provider or network code.  It defines the
small, serialisable contract shared by Hermes, an implementation Codex worker,
and the independent VPS audit worker.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp suitable for the ledger."""

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class OperationKind(str, Enum):
    READ_ONLY = "read_only"
    TEST = "test"
    CODE_CHANGE = "code_change"
    CONFIG_CHANGE = "config_change"
    AUDIO_PIPELINE_CHANGE = "audio_pipeline_change"
    SYSTEM_RECONFIGURATION = "system_reconfiguration"
    ROUTING_CHANGE = "routing_change"
    RESTART = "restart"
    DEPLOY = "deploy"
    SECURITY = "security"
    DESTRUCTIVE = "destructive"


class TaskState(str, Enum):
    REQUESTED = "REQUESTED"
    PLANNED = "PLANNED"
    IMPLEMENTING = "IMPLEMENTING"
    VERIFYING = "VERIFYING"
    APPROVED = "APPROVED"
    DEPLOYED = "DEPLOYED"
    NEEDS_FIX = "NEEDS_FIX"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class AuditStatus(str, Enum):
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class WorkerRole(str, Enum):
    IMPLEMENTER = "implementer"
    AUDITOR = "auditor"


class WorkerState(str, Enum):
    READY = "ready"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"
    STOPPING = "stopping"
    ERROR = "error"


def _as_operation(value: OperationKind | str) -> OperationKind:
    if isinstance(value, OperationKind):
        return value
    try:
        return OperationKind(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in OperationKind)
        raise ValueError(f"unknown operation {value!r}; expected one of: {allowed}") from exc


@dataclass(frozen=True)
class TechnicalTask:
    """A single logical technical change, independent of its worker."""

    summary: str
    operation: OperationKind | str
    repo_path: str
    branch: str | None = None
    rollback_plan: str = "Revert the task branch before deployment."
    task_id: str = field(default_factory=lambda: f"tech-{uuid.uuid4().hex}")
    state: TaskState = TaskState.REQUESTED
    implementer: str | None = None
    requires_confirmation: bool | None = None
    user_confirmed: bool = False
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.summary.strip():
            raise ValueError("task summary must not be empty")
        if not self.repo_path.strip():
            raise ValueError("repo_path must not be empty")
        object.__setattr__(self, "operation", _as_operation(self.operation))
        if self.requires_confirmation is None:
            object.__setattr__(self, "requires_confirmation", AuditGate.requires_confirmation(self.operation))

    @property
    def audit_required(self) -> bool:
        return AuditGate.requires_audit(self.operation)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "summary": self.summary,
            "operation": self.operation.value,
            "repo_path": self.repo_path,
            "branch": self.branch,
            "rollback_plan": self.rollback_plan,
            "state": self.state.value,
            "implementer": self.implementer,
            "requires_confirmation": bool(self.requires_confirmation),
            "user_confirmed": bool(self.user_confirmed),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TechnicalTask":
        return cls(
            task_id=str(data.get("task_id") or f"tech-{uuid.uuid4().hex}"),
            summary=str(data["summary"]),
            operation=_as_operation(str(data["operation"])),
            repo_path=str(data["repo_path"]),
            branch=data.get("branch"),
            rollback_plan=str(data.get("rollback_plan") or "Revert the task branch before deployment."),
            state=TaskState(str(data.get("state", TaskState.REQUESTED.value))),
            implementer=data.get("implementer"),
            requires_confirmation=data.get("requires_confirmation"),
            user_confirmed=bool(data.get("user_confirmed", False)),
            created_at=str(data.get("created_at") or utc_now()),
        )


@dataclass(frozen=True)
class AuditPacket:
    """Evidence collected by Hermes before asking the independent auditor."""

    task_id: str
    command: str
    expected: str
    actual: str
    exit_code: int | None = None
    changed_files: Sequence[str] = ()
    tests: Sequence[str] = ()
    health: Sequence[str] = ()
    next_action: str = ""

    def evidence(self) -> list[str]:
        values = [*self.changed_files, *self.tests, *self.health]
        return [str(value) for value in values if str(value).strip()]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "command": self.command,
            "expected": self.expected,
            "actual": self.actual,
            "exit_code": self.exit_code,
            "changed_files": list(self.changed_files),
            "tests": list(self.tests),
            "health": list(self.health),
            "next_action": self.next_action,
        }


@dataclass(frozen=True)
class AuditVerdict:
    """Strict, machine-readable result from the VPS Codex auditor."""

    status: AuditStatus | str
    rationale: str
    evidence: Sequence[str] = ()
    issues: Sequence[str] = ()
    improvement_plan: Sequence[str] = ()
    production_ready: bool = False
    rollback_plan: str = ""

    def __post_init__(self) -> None:
        try:
            status = self.status if isinstance(self.status, AuditStatus) else AuditStatus(self.status)
        except ValueError as exc:
            raise ValueError(f"unknown audit status: {self.status!r}") from exc
        object.__setattr__(self, "status", status)
        if not self.rationale.strip():
            raise ValueError("audit rationale must not be empty")
        if status in {AuditStatus.PASS, AuditStatus.PASS_WITH_WARNINGS} and not any(
            str(item).strip() for item in self.evidence
        ):
            raise ValueError("a passing audit must include evidence")
        if status not in {AuditStatus.PASS, AuditStatus.PASS_WITH_WARNINGS} and self.production_ready:
            raise ValueError("only a passing audit can be production-ready")
        if status in {AuditStatus.FAIL, AuditStatus.BLOCKED} and not any(
            str(item).strip() for item in self.improvement_plan
        ):
            raise ValueError("a failed or blocked audit must include an improvement plan")

    @property
    def passed(self) -> bool:
        return self.status in {AuditStatus.PASS, AuditStatus.PASS_WITH_WARNINGS}

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
            "issues": list(self.issues),
            "improvement_plan": list(self.improvement_plan),
            "production_ready": self.production_ready,
            "rollback_plan": self.rollback_plan,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AuditVerdict":
        return cls(
            status=str(data["status"]),
            rationale=str(data.get("rationale") or ""),
            evidence=tuple(str(item) for item in data.get("evidence", ())),
            issues=tuple(str(item) for item in data.get("issues", ())),
            improvement_plan=tuple(str(item) for item in data.get("improvement_plan", ())),
            production_ready=bool(data.get("production_ready", False)),
            rollback_plan=str(data.get("rollback_plan") or ""),
        )

    @classmethod
    def from_json(cls, raw: str) -> "AuditVerdict":
        """Parse only a JSON object; prose or truncated output fails closed."""

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("audit output is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("audit output must be a JSON object")
        required = {
            "status",
            "rationale",
            "evidence",
            "issues",
            "improvement_plan",
            "production_ready",
            "rollback_plan",
        }
        missing = sorted(required - payload.keys())
        if missing:
            raise ValueError(f"audit output is missing required fields: {', '.join(missing)}")
        return cls.from_dict(payload)

    def voice_summary(self) -> str:
        """Return a short message that Junmai can read back over voice."""

        if self.passed:
            return f"監査は{self.status.value}です。次の工程へ進めます。"
        suggestions = "、".join(str(item) for item in self.improvement_plan[:3])
        return f"監査で改善が必要です。提案は、{suggestions}です。"


@dataclass(frozen=True)
class WorkerStatus:
    worker_id: str
    role: WorkerRole
    state: WorkerState
    last_heartbeat: str | None = None
    capabilities: Sequence[str] = ()
    message: str = ""

    @property
    def ready(self) -> bool:
        return self.state is WorkerState.READY


@dataclass(frozen=True)
class WorkerResult:
    job_id: str
    worker_id: str
    state: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""


class CodexWorker(Protocol):
    """Common boundary for local and VPS Codex workers."""

    worker_id: str
    role: WorkerRole

    def status(self) -> WorkerStatus: ...

    def submit(self, task: TechnicalTask, prompt: str) -> str: ...

    def collect_result(self, job_id: str) -> WorkerResult: ...

    def cancel(self, job_id: str) -> None: ...


class AuditGate:
    """Central policy for when independent Codex review is mandatory."""

    _AUDITED = {
        OperationKind.CODE_CHANGE,
        OperationKind.CONFIG_CHANGE,
        OperationKind.AUDIO_PIPELINE_CHANGE,
        OperationKind.SYSTEM_RECONFIGURATION,
        OperationKind.ROUTING_CHANGE,
        OperationKind.RESTART,
        OperationKind.DEPLOY,
        OperationKind.SECURITY,
        OperationKind.DESTRUCTIVE,
    }
    _CONFIRMATION_REQUIRED = {
        OperationKind.SECURITY,
        OperationKind.DESTRUCTIVE,
        OperationKind.DEPLOY,
    }

    @classmethod
    def requires_audit(cls, operation: OperationKind | str) -> bool:
        return _as_operation(operation) in cls._AUDITED

    @classmethod
    def requires_confirmation(cls, operation: OperationKind | str) -> bool:
        return _as_operation(operation) in cls._CONFIRMATION_REQUIRED

    @classmethod
    def should_block_without_verdict(cls, operation: OperationKind | str) -> bool:
        return cls.requires_audit(operation)


class WorkerUnavailable(RuntimeError):
    """Raised when no suitable Codex worker is ready."""
