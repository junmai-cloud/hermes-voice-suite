import pytest

from voice_suite.budget import VoiceBudget


def test_budget_rejects_bitrate_above_mobile_safe_limit():
    with pytest.raises(ValueError, match="bitrate"):
        VoiceBudget(discord_bitrate_kbps=64)


def test_budget_estimates_bidirectional_mobile_usage():
    budget = VoiceBudget(discord_bitrate_kbps=32)
    assert budget.discord_mb_per_hour() == pytest.approx(28.8)
    assert budget.monthly_gb(hours_per_day=1) == pytest.approx(0.864)


def test_budget_limits_turn_duration():
    budget = VoiceBudget(max_turn_seconds=20)
    assert budget.accepts_turn(20) is True
    assert budget.accepts_turn(20.1) is False
