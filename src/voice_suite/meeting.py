"""Real-time meeting policy independent of Discord/STT/TTS providers."""

from dataclasses import dataclass, field
from enum import Enum


class MeetingMode(str, Enum):
    DRIVING = "driving"
    NORMAL = "normal"


@dataclass(frozen=True)
class MeetingPolicy:
    mode: MeetingMode = MeetingMode.DRIVING
    max_reply_seconds: int = 45
    require_confirmation_for_actions: bool = True


@dataclass
class MeetingOrchestrator:
    """Turn-taking and safety policy for the future Discord voice adapter."""

    policy: MeetingPolicy = field(default_factory=MeetingPolicy)
    transcript: list[tuple[str, str]] = field(default_factory=list)

    def user_turn(self, text: str) -> str:
        """Normalize a user turn; never manufacture an assistant echo."""
        cleaned = " ".join(text.split())
        if not cleaned:
            return ""
        self.transcript.append(("user", cleaned))
        return cleaned

    def clarification_reply(self) -> str:
        """Ask for a repeat when no usable speech was detected."""
        return "すみません、うまく聞き取れませんでした。もう一度お願いします。"

    def prepare_reply(self, reply: str, *, action: str | None = None) -> str:
        """Apply driving-mode constraints before TTS playback."""
        cleaned = " ".join(reply.split())
        if not cleaned:
            return ""
        if action and self.policy.require_confirmation_for_actions:
            cleaned += " 実行する場合は、明示的に『実行して』と言ってください。"
        if self.policy.mode is MeetingMode.DRIVING and len(cleaned) > 420:
            suffix = "。詳しい内容は運転終了後に確認できます。"
            cleaned = cleaned[: 420 - len(suffix)].rstrip(" 、。") + suffix
        self.transcript.append(("assistant", cleaned))
        return cleaned

    def meeting_close(self) -> str:
        """Produce a short spoken closeout from the latest turns."""
        user_turns = [text for role, text in self.transcript if role == "user"]
        if not user_turns:
            return "今日はまだ決定事項はありません。"
        return f"今日の会議では、直近の話題を{len(user_turns)}件整理しました。必要なら次に一つずつ進めます。"
