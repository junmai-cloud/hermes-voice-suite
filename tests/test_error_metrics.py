from voice_suite.metrics import SessionMetrics


def test_metrics_count_errors_without_error_text():
    metrics = SessionMetrics()
    metrics.record_error()
    assert metrics.snapshot()["errors"] == 1
    assert "エラー: 1回" in metrics.report()
    assert "Traceback" not in metrics.report()
