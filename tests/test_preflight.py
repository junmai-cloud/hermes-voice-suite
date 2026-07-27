from voice_suite.preflight import check_environment


def test_preflight_does_not_print_or_return_secret(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "super-secret-token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    results = check_environment()
    text = " ".join(f"{r.name} {r.detail}" for r in results)
    assert "super-secret-token" not in text
    assert any(r.name == "OPENAI_API_KEY" and not r.ok for r in results)


def test_preflight_reports_required_tools(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token")
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    results = check_environment()
    names = {r.name for r in results}
    assert {"DISCORD_BOT_TOKEN", "OPENAI_API_KEY", "ffmpeg", "hermes"} <= names
