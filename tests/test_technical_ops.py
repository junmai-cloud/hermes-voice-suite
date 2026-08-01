import json

import pytest

from voice_suite.technical_ops import (
    AuditGate,
    AuditStatus,
    AuditVerdict,
    OperationKind,
    TechnicalTask,
)


def test_audit_gate_only_escalates_logical_changes():
    assert not AuditGate.requires_audit(OperationKind.READ_ONLY)
    assert not AuditGate.requires_audit(OperationKind.TEST)
    assert AuditGate.requires_audit(OperationKind.CODE_CHANGE)
    assert AuditGate.requires_audit(OperationKind.AUDIO_PIPELINE_CHANGE)
    assert AuditGate.requires_confirmation(OperationKind.DEPLOY)
    assert AuditGate.requires_confirmation(OperationKind.SECURITY)
    assert not AuditGate.requires_confirmation(OperationKind.CONFIG_CHANGE)


def test_task_round_trip_sets_confirmation_policy():
    task = TechnicalTask("change routing", OperationKind.ROUTING_CHANGE, ".")
    restored = TechnicalTask.from_dict(task.to_dict())
    assert restored.operation is OperationKind.ROUTING_CHANGE
    assert restored.audit_required
    assert restored.requires_confirmation is False


def test_passing_audit_requires_evidence_and_strict_json():
    with pytest.raises(ValueError, match="evidence"):
        AuditVerdict(AuditStatus.PASS, "looks good")
    verdict = AuditVerdict.from_json(
        json.dumps(
            {
                "status": "PASS_WITH_WARNINGS",
                "rationale": "tested",
                "evidence": ["pytest: passed"],
                "issues": ["warning"],
                "improvement_plan": ["monitor latency"],
                "production_ready": True,
                "rollback_plan": "revert branch",
            }
        )
    )
    assert verdict.passed
    with pytest.raises(ValueError, match="valid JSON"):
        AuditVerdict.from_json("PASS: tested")
    with pytest.raises(ValueError, match="missing required fields"):
        AuditVerdict.from_json('{"status":"FAIL","rationale":"incomplete"}')


def test_non_passing_audit_cannot_be_production_ready():
    with pytest.raises(ValueError, match="production-ready"):
        AuditVerdict(
            AuditStatus.FAIL,
            "test failed",
            issues=["failure"],
            improvement_plan=["fix the failure"],
            production_ready=True,
        )


def test_failed_audit_exposes_a_short_voice_improvement_message():
    verdict = AuditVerdict(
        AuditStatus.FAIL,
        "latency regression",
        issues=["latency increased"],
        improvement_plan=["reduce chunk size", "rerun latency test"],
    )
    assert "改善が必要" in verdict.voice_summary()
    assert "reduce chunk size" in verdict.voice_summary()
