"""Production entry point for the separate Codex Discord bot."""

from __future__ import annotations

import os
import sys

from .adapters import OpenAISynthesizer, OpenAITranscriber
from .codex_discord_bot import (
    CodexDiscordBridge,
    CodexDiscordSettings,
    RemoteCodexChatWorker,
)


def check_worker(settings: CodexDiscordSettings, *, worker=None) -> dict[str, object]:
    """Require the authenticated prompt-only worker, not configuration alone."""
    client = worker or RemoteCodexChatWorker(
        settings.chat_worker_url,
        settings.chat_worker_token,
        timeout=min(settings.worker_timeout, 10.0),
    )
    status = client.status()
    capabilities = set(status.get("capabilities", ()))
    if status.get("state") != "ready":
        raise RuntimeError("Codex Chat Worker is not ready")
    if not {"prompt-only", "read-only"}.issubset(capabilities):
        raise RuntimeError("Codex Chat Worker is missing required safety capabilities")
    return status


def main() -> None:
    try:
        settings = CodexDiscordSettings.from_env()
        if "--check" in sys.argv[1:]:
            check_worker(settings)
            print("codex-voice-bot preflight")
            print("OK configuration: dedicated credentials and restrictions are present")
            print("OK worker: authenticated prompt-only read-only health is ready")
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
