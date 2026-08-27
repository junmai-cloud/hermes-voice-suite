from dataclasses import dataclass

import pytest

from voice_suite.technical_ledger import TechnicalLedger
from voice_suite.technical_ops import (
    AuditPacket,
    AuditStatus,
    AuditVerdict,
    CodexWorker,
    WorkerRole,
    WorkerState,
    WorkerStatus,
    WorkerResult,
)
from voice_suite.technical_service import TechnicalOrchestrator, WorkerPool


@dataclass
class FakeWorker:
    worker_id: str
    ready: bool = True
    role: WorkerRole = WorkerRole.IMPLEMENTER

    def __post_init__(self):
        self.jobs = []

    def status(self):
        return WorkerStatus(
            self.worker_id,
            self.role,
            WorkerState.READY if self.ready else WorkerState.UNAVAILABLE,
            capabilities=("fake",),
        )

    def submit(self, task, prompt):
        job_id = f"{self.worker_id}-job-{len(self.jobs) + 1}"
        self.jobs.append((job_id, task.task_id, prompt))
        return job_id

    def collect_result(self, job_id):
        return WorkerResult(job_id, self.worker_id, "completed", 0, "", "")

    def cancel(self, job_id):
        return None


def _orchestrator(tmp_path, *, local_ready=True, auditor=None):
    ledger = TechnicalLedger(tmp_path / "technical.db")
    local = FakeWorker("local-codex", local_ready)
    vps = FakeWorker("vps-codex", True)
    return TechnicalOrchestrator(
        ledger,
        vps_worker=vps,
        local_worker=local,
        auditor_worker=auditor or FakeWorker("vps-codex-auditor", True, WorkerRole.AUDITOR),
    ), ledger, local, vps


def test_local_worker_is_preferred_when_ready(tmp_path):
    orchestrator, ledger, local, _ = _orchestrator(tmp_path)
    task = orchestrator.register("small change", "code_change", ".", branch="codex/test")
    result = orchestrator.dispatch(task.task_id, "implement the small change")
    assert result.worker_id == "local-codex"
    assert ledger.get(task.task_id)["implementer"] == "local-codex"


def test_vps_worker_is_fallback_when_local_is_unavailable(tmp_path):
    orchestrator, ledger, _, vps = _orchestrator(tmp_path, local_ready=False)
    task = orchestrator.register("small change", "code_change", ".", branch="codex/test")
    result = orchestrator.dispatch(task.task_id, "implement the small change")
    assert result.worker_id == "vps-codex"
    assert vps.jobs
    assert ledger.get(task.task_id)["implementer"] == "vps-codex"


def test_audit_submission_and_completion_are_separate_from_implementation(tmp_path):
    orchestrator, ledger, _, _ = _orchestrator(tmp_path)
    task = orchestrator.register("small change", "code_change", ".", branch="codex/test")
    implementation = orchestrator.dispatch(task.task_id, "implement the small change")
    packet = AuditPacket(
        task.task_id,
        "pytest -q",
        "all pass",
        "all pass",
        0,
        changed_files=["src/example.py"],
        tests=["pytest: passed"],
        health=["service: healthy"],
    )
    audit_job = orchestrator.submit_audit(task.task_id, packet, "audit this change")
    assert audit_job.worker_id == "vps-codex-auditor"
    assert ledger.get(task.task_id)["state"] == "VERIFYING"
    orchestrator.complete_audit(
        task.task_id,
        '{"status":"PASS","rationale":"evidence checked","evidence":["pytest: passed"],"issues":[],"improvement_plan":[],"production_ready":true,"rollback_plan":"revert branch"}',
    )
    assert orchestrator.can_report_complete(task.task_id)
    assert ledger.get(task.task_id)["auditor"] == "vps-codex-auditor"
    assert implementation.worker_id == "local-codex"


def test_unavailable_auditor_blocks_task(tmp_path):
    auditor = FakeWorker("vps-codex-auditor", False, WorkerRole.AUDITOR)
    orchestrator, ledger, _, _ = _orchestrator(tmp_path, auditor=auditor)
    task = orchestrator.register("small change", "code_change", ".", branch="codex/test")
    orchestrator.dispatch(task.task_id, "implement the small change")
    packet = AuditPacket(task.task_id, "pytest -q", "pass", "pass", 0, tests=["pass"])
    with pytest.raises(Exception, match="auditor is not ready"):
        orchestrator.submit_audit(task.task_id, packet, "audit this change")
    assert ledger.get(task.task_id)["state"] == "BLOCKED"


def test_sensitive_operation_requires_explicit_confirmation(tmp_path):
    orchestrator, ledger, _, _ = _orchestrator(tmp_path)
    task = orchestrator.register("deploy change", "deploy", ".", branch="codex/deploy")
    with pytest.raises(ValueError, match="confirmation"):
        orchestrator.dispatch(task.task_id, "prepare deployment")
    orchestrator.confirm(task.task_id)
    result = orchestrator.dispatch(task.task_id, "prepare deployment")
    assert result.worker_id == "local-codex"
    assert ledger.get(task.task_id)["user_confirmed"] is True


def test_audited_dispatch_requires_a_branch(tmp_path):
    orchestrator, _, _, _ = _orchestrator(tmp_path)
    task = orchestrator.register("unsafe direct change", "code_change", ".")
    with pytest.raises(ValueError, match="Git branch"):
        orchestrator.dispatch(task.task_id, "change the production checkout")


def test_failed_audit_requires_user_acceptance_before_repair(tmp_path):
    orchestrator, ledger, _, _ = _orchestrator(tmp_path)
    task = orchestrator.register("repairable change", "code_change", ".", branch="codex/repair")
    orchestrator.dispatch(task.task_id, "implement the change")
    packet = AuditPacket(task.task_id, "pytest -q", "pass", "failed", 1, tests=["pytest: failed"])
    orchestrator.submit_audit(task.task_id, packet, "audit the change")
    orchestrator.complete_audit(
        task.task_id,
        '{"status":"FAIL","rationale":"test failed","evidence":["pytest: failed"],"issues":["failure"],"improvement_plan":["fix the failing test"],"production_ready":false,"rollback_plan":"revert branch"}',
    )
    assert ledger.get(task.task_id)["state"] == "NEEDS_FIX"
    with pytest.raises(ValueError, match="improvement plan"):
        orchestrator.dispatch(task.task_id, "apply the improvement plan")
    orchestrator.confirm(task.task_id)
    assert orchestrator.dispatch(task.task_id, "apply the improvement plan").worker_id == "local-codex"


def test_worker_pool_binds_each_job_to_one_ready_slot():
    first = FakeWorker("local-codex-1")
    second = FakeWorker("local-codex-2")
    pool = WorkerPool([first, second], pool_id="local-burst")
    task = type("Task", (), {"task_id": "task-1"})()
    job1 = pool.submit(task, "first")
    first.ready = False
    job2 = pool.submit(task, "second")
    assert job1 == "local-codex-1-job-1"
    assert job2 == "local-codex-2-job-1"
    assert pool.collect_result(job1).state == "completed"
    assert pool.status().ready


def test_worker_pool_fails_closed_when_no_slot_is_ready():
    pool = WorkerPool([FakeWorker("local-codex-1", False)], pool_id="local-burst")
    assert not pool.status().ready
    with pytest.raises(Exception, match="no ready worker slot"):
        pool.submit(type("Task", (), {"task_id": "task-1"})(), "work")
