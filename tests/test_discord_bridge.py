import pytest

from voice_suite.discord_bridge import VoiceBotSettings


def test_voice_settings_require_token(monkeypatch):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="DISCORD_BOT_TOKEN"):
        VoiceBotSettings.from_env()


def test_voice_settings_parse_ids(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
    monkeypatch.setenv("DISCORD_GUILD_ID", "123")
    monkeypatch.setenv("DISCORD_VOICE_CHANNEL_ID", "456")
    settings = VoiceBotSettings.from_env()
    assert settings.guild_id == 123
    assert settings.voice_channel_id == 456
