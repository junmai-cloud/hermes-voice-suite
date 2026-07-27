import pytest

from voice_suite.discord_bridge import VoiceBotSettings


def test_voice_settings_parse_allowed_user_id(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
    monkeypatch.setenv("DISCORD_ALLOWED_USER_ID", "789")
    settings = VoiceBotSettings.from_env()
    assert settings.allowed_user_id == 789


def test_voice_settings_reject_invalid_allowed_user_id(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
    monkeypatch.setenv("DISCORD_ALLOWED_USER_ID", "not-a-number")
    with pytest.raises(ValueError):
        VoiceBotSettings.from_env()
