"""Privacy-preserving operational metrics for voice sessions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SessionMetrics:
    """Keep counters only; never accept transcript or audio payloads."""

    max_voice_mb: float = 40.0
    voice_bytes_sent: int = 0
    voice_bytes_received: int = 0
    turns: int = 0
    total_turn_seconds: float = 0.0
    stt_bytes: int = 0
    reply_seconds: float = 0.0
    interruptions: int = 0

    def add_voice_bytes(self, *, sent: int, received: int) -> None:
        self.voice_bytes_sent += max(0, sent)
        self.voice_bytes_received += max(0, received)

    def record_turn(
        self,
        *,
        duration_seconds: float,
        stt_bytes: int,
        reply_seconds: float,
        interrupted: bool = False,
    ) -> None:
        self.turns += 1
        self.total_turn_seconds += max(0.0, duration_seconds)
        self.stt_bytes += max(0, stt_bytes)
        self.reply_seconds += max(0.0, reply_seconds)
        self.interruptions += int(interrupted)

    def over_budget(self) -> bool:
        return (self.voice_bytes_sent + self.voice_bytes_received) > self.max_voice_mb * 1_000_000

    def report(self) -> str:
        total_mb = (self.voice_bytes_sent + self.voice_bytes_received) / 1_000_000
        status = "通信量超過" if self.over_budget() else "予算内"
        return (
            f"音声セッション状況。通信量: {total_mb:.1f} MB（{status}）。"
            f"発話数: {self.turns}。"
            f"処理時間: {self.reply_seconds:.1f}秒。"
            f"割り込み: {self.interruptions}回。"
        )

    def snapshot(self) -> dict[str, int | float]:
        return {
            "voice_bytes_sent": self.voice_bytes_sent,
            "voice_bytes_received": self.voice_bytes_received,
            "turns": self.turns,
            "total_turn_seconds": self.total_turn_seconds,
            "stt_bytes": self.stt_bytes,
            "reply_seconds": self.reply_seconds,
            "interruptions": self.interruptions,
        }
