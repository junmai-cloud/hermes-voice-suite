"""Safe, non-network startup checks for the voice bot."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def check_environment() -> list[CheckResult]:
    results: list[CheckResult] = []
    for name in (
        "DISCORD_BOT_TOKEN",
        "OPENAI_API_KEY",
        "DISCORD_GUILD_ID",
        "DISCORD_VOICE_CHANNEL_ID",
        "DISCORD_ALLOWED_USER_ID",
    ):
        present = bool(os.environ.get(name, "").strip())
        results.append(CheckResult(name, present, "設定済み" if present else "未設定"))
    for tool in ("ffmpeg", "hermes"):
        path = shutil.which(tool)
        results.append(CheckResult(tool, path is not None, "利用可能" if path else "PATHに未検出"))
    try:
        import discord

        pycord_ready = hasattr(discord, "Bot") and hasattr(discord, "sinks")
        detail = "Pycord voice API available" if pycord_ready else "Pycord is required (discord.Bot/discord.sinks missing)"
    except ImportError:
        pycord_ready = False
        detail = "Pycord is required (discord module not installed)"
    results.append(CheckResult("pycord", pycord_ready, detail))
    return results


def format_report(results: list[CheckResult]) -> str:
    lines = ["voice-bot preflight（ネットワーク接続なし）"]
    lines.extend(f"{'OK' if result.ok else 'NG'} {result.name}: {result.detail}" for result in results)
    return "\n".join(lines)
