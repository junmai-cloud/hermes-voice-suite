"""Explicit mobile data and turn-length budget for voice mode."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceBudget:
    """Conservative defaults for a voice-only mobile meeting.

    Discord traffic is counted in both directions. Protocol overhead and
    occasional control traffic are not hidden in the estimate; production
    monitoring should report actual bytes as a separate metric.
    """

    discord_bitrate_kbps: int = 32
    max_turn_seconds: int = 20
    max_reply_seconds: int = 45
    max_daily_hours: float = 2.0

    def __post_init__(self) -> None:
        if not 8 <= self.discord_bitrate_kbps <= 32:
            raise ValueError("bitrate must be between 8 and 32 kbps for mobile-safe mode")
        if self.max_turn_seconds <= 0 or self.max_reply_seconds <= 0:
            raise ValueError("turn and reply limits must be positive")

    def discord_mb_per_hour(self) -> float:
        return self.discord_bitrate_kbps * 3600 / 8 / 1000 * 2

    def monthly_gb(self, *, hours_per_day: float | None = None, days: int = 30) -> float:
        hours = self.max_daily_hours if hours_per_day is None else hours_per_day
        return self.discord_mb_per_hour() * hours * days / 1000

    def accepts_turn(self, seconds: float) -> bool:
        return 0 <= seconds <= self.max_turn_seconds
