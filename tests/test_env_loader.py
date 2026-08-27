from pathlib import Path

from voice_suite.env_loader import load_dotenv_allowlisted


def test_dotenv_loader_only_imports_allowlisted_keys(monkeypatch, tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "CODEX_CHAT_WORKER_TOKEN='dedicated-token'\n"
        "DISCORD_BOT_TOKEN=hermes-token\n"
        "export CODEX_CHAT_PORT=8777\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("CODEX_CHAT_WORKER_TOKEN", raising=False)
    monkeypatch.delenv("CODEX_CHAT_PORT", raising=False)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)

    loaded = load_dotenv_allowlisted(
        env_file,
        allowed_keys={"CODEX_CHAT_WORKER_TOKEN", "CODEX_CHAT_PORT"},
    )

    assert loaded == {"CODEX_CHAT_WORKER_TOKEN", "CODEX_CHAT_PORT"}
    assert loaded and __import__("os").environ["CODEX_CHAT_WORKER_TOKEN"] == "dedicated-token"
    assert __import__("os").environ["CODEX_CHAT_PORT"] == "8777"
    assert "DISCORD_BOT_TOKEN" not in __import__("os").environ
