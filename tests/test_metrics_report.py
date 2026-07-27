from voice_suite.metrics import SessionMetrics


def test_metrics_report_is_content_free():
    metrics = SessionMetrics()
    metrics.add_voice_bytes(sent=1_000_000, received=2_000_000)
    metrics.record_turn(duration_seconds=4, stt_bytes=300, reply_seconds=2)
    report = metrics.report()
    assert "3.0 MB" in report
    assert "発話数: 1" in report
    assert "通信量超過" not in report
    assert "会話" not in report


def test_metrics_report_warns_when_over_budget():
    metrics = SessionMetrics(max_voice_mb=1)
    metrics.add_voice_bytes(sent=600_000, received=600_000)
    assert "通信量超過" in metrics.report()
