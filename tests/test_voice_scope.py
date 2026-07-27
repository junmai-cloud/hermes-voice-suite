from voice_suite.discord_bridge import VoiceBotSettings


def test_settings_authorize_only_configured_scope():
    settings = VoiceBotSettings("token", guild_id=10, voice_channel_id=20, allowed_user_id=30)
    assert settings.authorizes(user_id=30, guild_id=10, voice_channel_id=20)
    assert not settings.authorizes(user_id=31, guild_id=10, voice_channel_id=20)
    assert not settings.authorizes(user_id=30, guild_id=11, voice_channel_id=20)
    assert not settings.authorizes(user_id=30, guild_id=10, voice_channel_id=21)


def test_unset_scope_remains_compatible():
    settings = VoiceBotSettings("token")
    assert settings.authorizes(user_id=1, guild_id=2, voice_channel_id=3)
