import json

import pytest

from voice_suite.codex_discord_bot import (
    CodexDiscordSettings,
    CodexRemoteBrain,
    RemoteCodexChatWorker,
)


def _set_chat_worker_env(monkeypatch):
    monkeypatch.setenv("CODEX_CHAT_WORKER_URL", "http://chat-worker.test")
    monkeypatch.setenv("CODEX_CHAT_WORKER_TOKEN", "chat-worker-test-token")


def test_codex_settings_use_separate_token_and_ids(monkeypatch):
    monkeypatch.setenv("CODEX_DISCORD_BOT_TOKEN", "codex-test-token")
    _set_chat_worker_env(monkeypatch)
    monkeypatch.setenv("CODEX_DISCORD_GUILD_ID", "1539771881731788990")
    monkeypatch.setenv("CODEX_DISCORD_TEXT_CHANNEL_ID", "1539771882642079817")
    monkeypatch.setenv("CODEX_DISCORD_VOICE_CHANNEL_ID", "1539771882642079818")
    settings = CodexDiscordSettings.from_env()
    assert settings.token == "codex-test-token"
    assert settings.guild_id == 1539771881731788990
    assert settings.text_channel_id == 1539771882642079817
    assert settings.voice_channel_id == 1539771882642079818
    assert settings.chat_worker_url == "http://chat-worker.test"
    assert settings.chat_worker_token == "chat-worker-test-token"


def test_codex_settings_require_dedicated_bot_token(monkeypatch):
    monkeypatch.delenv("CODEX_DISCORD_BOT_TOKEN", raising=False)
    _set_chat_worker_env(monkeypatch)
    with pytest.raises(RuntimeError, match="CODEX_DISCORD_BOT_TOKEN"):
        CodexDiscordSettings.from_env()


def test_codex_settings_reject_hermes_token_reuse(monkeypatch):
    monkeypatch.setenv("CODEX_DISCORD_BOT_TOKEN", "same-token")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "same-token")
    _set_chat_worker_env(monkeypatch)
    with pytest.raises(RuntimeError, match="differ from DISCORD_BOT_TOKEN"):
        CodexDiscordSettings.from_env()


def test_codex_settings_reject_technical_worker_token_reuse(monkeypatch):
    monkeypatch.setenv("CODEX_DISCORD_BOT_TOKEN", "codex-test-token")
    monkeypatch.setenv("CODEX_WORKER_TOKEN", "same-token")
    monkeypatch.setenv("CODEX_CHAT_WORKER_URL", "http://chat-worker.test")
    monkeypatch.setenv("CODEX_CHAT_WORKER_TOKEN", "same-token")
    with pytest.raises(RuntimeError, match="differ from CODEX_WORKER_TOKEN"):
        CodexDiscordSettings.from_env()


def test_codex_settings_require_dedicated_chat_worker_credentials(monkeypatch):
    monkeypatch.setenv("CODEX_DISCORD_BOT_TOKEN", "codex-test-token")
    monkeypatch.setenv("CODEX_WORKER_TOKEN", "shared-worker-token")
    with pytest.raises(RuntimeError, match="CODEX_CHAT_WORKER_URL"):
        CodexDiscordSettings.from_env()
    monkeypatch.setenv("CODEX_CHAT_WORKER_URL", "http://chat-worker.test")
    with pytest.raises(RuntimeError, match="CODEX_CHAT_WORKER_TOKEN"):
        CodexDiscordSettings.from_env()


def test_codex_text_authorization_is_guild_and_channel_scoped(monkeypatch):
    monkeypatch.setenv("CODEX_DISCORD_BOT_TOKEN", "codex-test-token")
    _set_chat_worker_env(monkeypatch)
    monkeypatch.setenv("CODEX_DISCORD_GUILD_ID", "10")
    monkeypatch.setenv("CODEX_DISCORD_TEXT_CHANNEL_ID", "20")
    settings = CodexDiscordSettings.from_env()
    assert settings.authorizes_text(user_id=1, guild_id=10, channel_id=20)
    assert not settings.authorizes_text(user_id=1, guild_id=11, channel_id=20)
    assert not settings.authorizes_text(user_id=1, guild_id=10, channel_id=21)


def test_greeting_is_answered_without_worker_call():
    class FailingWorker:
        def submit(self, *_args):
            raise AssertionError("greetings must not start a Codex job")

    settings = CodexDiscordSettings(
        token="codex-test-token",
        guild_id=10,
        text_channel_id=20,
        voice_channel_id=30,
        allowed_user_id=None,
        chat_worker_url="http://127.0.0.1:8767",
        chat_worker_token="chat-worker-test-token",
    )
    assert "こんにちは" in CodexRemoteBrain(settings, worker=FailingWorker()).answer("こんにちは")


def test_brain_sends_only_prompt_to_chat_worker():
    class RecordingChatWorker:
        def __init__(self):
            self.prompts = []

        def answer(self, prompt):
            self.prompts.append(prompt)
            return "専用Chat Workerの回答"

    settings = CodexDiscordSettings(
        token="codex-test-token",
        guild_id=None,
        text_channel_id=None,
        voice_channel_id=None,
        allowed_user_id=None,
        chat_worker_url="http://chat-worker.test",
        chat_worker_token="chat-worker-test-token",
    )
    worker = RecordingChatWorker()
    assert CodexRemoteBrain(settings, worker=worker).answer("調べて") == "専用Chat Workerの回答"
    assert len(worker.prompts) == 1
    assert "ユーザーの依頼:" in worker.prompts[0]


def test_remote_chat_worker_posts_prompt_only(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"reply":"ok"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    worker = RemoteCodexChatWorker(
        "http://chat-worker.test/",
        "chat-worker-test-token",
        timeout=7.5,
    )

    assert worker.answer("hello") == "ok"
    assert captured == {
        "url": "http://chat-worker.test/chat",
        "body": {"prompt": "hello"},
        "authorization": "Bearer chat-worker-test-token",
        "timeout": 7.5,
    }
