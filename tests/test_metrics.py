from voice_suite.metrics import SessionMetrics


def test_metrics_track_bytes_and_turns_without_transcript():
    metrics = SessionMetrics()
    metrics.add_voice_bytes(sent=100, received=200)
    metrics.record_turn(duration_seconds=3.2, stt_bytes=500, reply_seconds=1.4, interrupted=True)
    snapshot = metrics.snapshot()
    assert snapshot == {
        "voice_bytes_sent": 100,
        "voice_bytes_received": 200,
        "turns": 1,
        "total_turn_seconds": 3.2,
        "stt_bytes": 500,
        "reply_seconds": 1.4,
        "interruptions": 1,
    }
    assert "transcript" not in snapshot


def test_metrics_flags_budget_overrun():
    metrics = SessionMetrics(max_voice_mb=1)
    metrics.add_voice_bytes(sent=600_000, received=600_000)
    assert metrics.over_budget() is True
