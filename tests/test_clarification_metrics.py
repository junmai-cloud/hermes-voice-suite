from voice_suite.metrics import SessionMetrics


def test_metrics_count_clarifications_separately():
    metrics = SessionMetrics()
    metrics.record_clarification()
    assert metrics.snapshot()["clarifications"] == 1
    assert "聞き返し: 1回" in metrics.report()
