import json

import pytest

from voice_suite.technical_ledger import TechnicalLedger
from voice_suite.technical_ops import AuditPacket, AuditStatus, AuditVerdict, OperationKind, TaskState, TechnicalTask


def _implementing_task(ledger: TechnicalLedger, *, operation=OperationKind.CODE_CHANGE) -> TechnicalTask:
    task = TechnicalTask("change code", operation, ".")
    ledger.create(task)
    ledger.transition(task.task_id, TaskState.PLANNED)
    ledger.transition(task.task_id, TaskState.IMPLEMENTING)
    return task


def _packet(task_id: str, actual: str = "tests passed") -> AuditPacket:
    return AuditPacket(
        task_id=task_id,
        command="pytest -q",
        expected="all tests pass",
        actual=actual,
        exit_code=0,
        changed_files=["src/voice_suite/example.py"],
        tests=["pytest: passed"],
        health=["service: healthy"],
    )


def test_ledger_requires_packet_and_verdict_before_completion(tmp_path):
    ledger = TechnicalLedger(tmp_path / "technical.db")
    task = _implementing_task(ledger)
    assert not ledger.can_report_complete(task.task_id)
    with pytest.raises(ValueError, match="without an audit packet"):
        ledger.record_verdict(
            task.task_id,
            AuditVerdict(AuditStatus.FAIL, "not ready", improvement_plan=["collect the audit packet"]),
        )
    ledger.record_packet(_packet(task.task_id))
    ledger.record_verdict(
        task.task_id,
        AuditVerdict(AuditStatus.PASS, "all evidence is present", evidence=["pytest: passed"], production_ready=True),
    )
    assert ledger.get(task.task_id)["state"] == TaskState.APPROVED.value
    assert ledger.can_report_complete(task.task_id)


def test_failed_audit_returns_to_needs_fix(tmp_path):
    ledger = TechnicalLedger(tmp_path / "technical.db")
    task = _implementing_task(ledger)
    ledger.record_packet(_packet(task.task_id, actual="pytest failed"))
    ledger.record_verdict(
        task.task_id,
        AuditVerdict(
            AuditStatus.FAIL,
            "one test failed",
            issues=["failure"],
            improvement_plan=["fix the failing test"],
        ),
    )
    assert ledger.get(task.task_id)["state"] == TaskState.NEEDS_FIX.value


def test_ledger_redacts_secrets_and_has_no_audio_or_transcript_fields(tmp_path):
    ledger = TechnicalLedger(tmp_path / "technical.db")
    task = TechnicalTask("record token=super-secret", OperationKind.CODE_CHANGE, ".")
    ledger.create(task)
    ledger.transition(task.task_id, TaskState.PLANNED)
    ledger.transition(task.task_id, TaskState.IMPLEMENTING)
    packet = _packet(task.task_id, actual="API_KEY=super-secret password:another-secret")
    ledger.record_packet(packet)
    record = ledger.get(task.task_id)
    raw = json.dumps(record, ensure_ascii=False)
    assert "super-secret" not in raw
    assert "another-secret" not in raw
    assert "audio" not in record
    assert "transcript" not in record
    assert record["packet_json"]["actual"] == "API_KEY=<REDACTED> password: <REDACTED>"


def test_invalid_state_transition_is_rejected(tmp_path):
    ledger = TechnicalLedger(tmp_path / "technical.db")
    task = TechnicalTask("read logs", OperationKind.READ_ONLY, ".")
    ledger.create(task)
    with pytest.raises(ValueError, match="invalid task transition"):
        ledger.transition(task.task_id, TaskState.APPROVED)
