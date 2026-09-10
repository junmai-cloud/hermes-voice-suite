import pytest

from voice_suite.codex_worker import CodexCliWorker
from voice_suite.technical_ops import WorkerRole


def test_implementation_worker_rejects_danger_full_access():
    with pytest.raises(ValueError, match="unsupported Codex worker sandbox"):
        CodexCliWorker("vps-codex", role=WorkerRole.IMPLEMENTER, sandbox="danger-full-access")


def test_auditor_requires_read_only_sandbox():
    with pytest.raises(ValueError, match="auditor sandbox must be read-only"):
        CodexCliWorker("auditor", role=WorkerRole.AUDITOR, sandbox="workspace-write")


def test_expected_worker_sandboxes_are_allowed():
    CodexCliWorker("reader", role=WorkerRole.IMPLEMENTER, sandbox="read-only")
    CodexCliWorker("writer", role=WorkerRole.IMPLEMENTER, sandbox="workspace-write")
    CodexCliWorker("auditor", role=WorkerRole.AUDITOR, sandbox="read-only")
