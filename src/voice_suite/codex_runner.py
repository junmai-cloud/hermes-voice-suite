"""Production entry point for the separate Codex Discord bot."""

from __future__ import annotations

import os
import sys

from .adapters import OpenAISynthesizer, OpenAITranscriber
from .codex_discord_bot import CodexDiscordBridge, CodexDiscordSettings


def main() -> None:
    try:
        settings = CodexDiscordSettings.from_env()
        if "--check" in sys.argv[1:]:
            print("codex-voice-bot preflight")
            print("OK configuration: token and worker settings are present")
            return
        bridge = CodexDiscordBridge(
            settings,
            transcriber=OpenAITranscriber(
                model=os.environ.get("CODEX_STT_MODEL", "gpt-4o-mini-transcribe")
            ),
            synthesizer=OpenAISynthesizer(
                model=os.environ.get("CODEX_TTS_MODEL", "gpt-4o-mini-tts"),
                voice=os.environ.get("CODEX_TTS_VOICE", "alloy"),
            ),
        )
    except (RuntimeError, ValueError, ImportError) as exc:
        raise SystemExit(f"codex-voice-bot configuration error: {exc}") from None
    bridge.run()
