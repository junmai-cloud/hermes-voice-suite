from voice_suite.preflight import check_environment


def test_preflight_requires_restricted_voice_scope(monkeypatch):
    for name in (
        "DISCORD_BOT_TOKEN",
        "OPENAI_API_KEY",
        "DISCORD_GUILD_ID",
        "DISCORD_VOICE_CHANNEL_ID",
        "DISCORD_ALLOWED_USER_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    results = {result.name: result for result in check_environment()}
    assert not results["DISCORD_GUILD_ID"].ok
    assert not results["DISCORD_VOICE_CHANNEL_ID"].ok
    assert not results["DISCORD_ALLOWED_USER_ID"].ok
