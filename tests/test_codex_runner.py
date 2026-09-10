import pytest

from voice_suite.codex_discord_bot import CodexDiscordSettings
from voice_suite.codex_runner import check_worker


def settings():
    return CodexDiscordSettings(
        token="discord-token",
        guild_id=1,
        text_channel_id=2,
        voice_channel_id=3,
        allowed_user_id=4,
        chat_worker_url="http://127.0.0.1:8777",
        chat_worker_token="chat-token",
    )


class Worker:
    def __init__(self, status):
        self._status = status

    def status(self):
        return self._status


def test_preflight_requires_ready_safe_worker():
    result = check_worker(
        settings(),
        worker=Worker({"state": "ready", "capabilities": ["prompt-only", "read-only"]}),
    )
    assert result["state"] == "ready"


@pytest.mark.parametrize(
    "status, message",
    [
        ({"state": "unavailable", "capabilities": []}, "not ready"),
        ({"state": "ready", "capabilities": ["prompt-only"]}, "safety capabilities"),
    ],
)
def test_preflight_rejects_false_ready_states(status, message):
    with pytest.raises(RuntimeError, match=message):
        check_worker(settings(), worker=Worker(status))
