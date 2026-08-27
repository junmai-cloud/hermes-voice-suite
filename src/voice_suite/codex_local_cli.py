"""Run the isolated Codex JUNMAI Discord bot on the local PC.

This entry point starts both halves of the local path in one process:

    Discord -> Codex bot -> prompt-only local HTTP worker -> Codex CLI

It intentionally does not import Hermes' technical-operation service, worker,
auditor, or ledger modules.  The chat worker owns the immutable read-only
Codex invocation and the Discord bot owns the separate Discord token.
"""

from __future__ import annotations

import argparse
import os
import threading
from pathlib import Path
from typing import Sequence

from .adapters import OpenAISynthesizer, OpenAITranscriber
from .codex_chat import ChatWorkerHTTPServer, worker_from_environment
from .codex_discord_bot import CodexDiscordBridge, CodexDiscordSettings
from .env_loader import load_dotenv_allowlisted


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GUILD_ID = "1539771881731788990"
DEFAULT_TEXT_CHANNEL_ID = "1539771882642079817"
DEFAULT_VOICE_CHANNEL_ID = "1539771882642079818"

_LOCAL_ENV_KEYS = {
    "CODEX_DISCORD_BOT_TOKEN",
    "CODEX_CHAT_WORKER_TOKEN",
    "CODEX_CHAT_WORKER_URL",
    "CODEX_DISCORD_GUILD_ID",
    "CODEX_DISCORD_TEXT_CHANNEL_ID",
    "CODEX_DISCORD_VOICE_CHANNEL_ID",
    "CODEX_DISCORD_ALLOWED_USER_ID",
    "CODEX_CHAT_WORKER_TIMEOUT",
    "CODEX_CHAT_TIMEOUT",
    "CODEX_CHAT_MAX_PROMPT_CHARS",
    "CODEX_CHAT_MAX_RESPONSE_CHARS",
    "CODEX_CHAT_COMMAND",
    "CODEX_CHAT_WORKDIR",
    "CODEX_REPO_PATH",
    "CODEX_CHAT_HOST",
    "CODEX_CHAT_PORT",
    "CODEX_HOME",
    "OPENAI_API_KEY",
    "CODEX_STT_MODEL",
    "CODEX_TTS_MODEL",
    "CODEX_TTS_VOICE",
    "LANG",
    "LC_ALL",
    "NO_COLOR",
}


def load_local_environment(env_file: str | Path | None = None) -> set[str]:
    """Load only the local Codex bot settings from the ignored dotenv file."""

    loaded = load_dotenv_allowlisted(
        env_file or ROOT / ".env",
        allowed_keys=_LOCAL_ENV_KEYS,
    )
    os.environ.setdefault("CODEX_DISCORD_GUILD_ID", DEFAULT_GUILD_ID)
    os.environ.setdefault("CODEX_DISCORD_TEXT_CHANNEL_ID", DEFAULT_TEXT_CHANNEL_ID)
    os.environ.setdefault("CODEX_DISCORD_VOICE_CHANNEL_ID", DEFAULT_VOICE_CHANNEL_ID)
    os.environ.setdefault("CODEX_CHAT_WORKER_URL", "http://127.0.0.1:8777")
    os.environ.setdefault("CODEX_CHAT_HOST", "127.0.0.1")
    os.environ.setdefault("CODEX_CHAT_PORT", "8777")
    os.environ.setdefault("CODEX_CHAT_WORKDIR", str(ROOT))
    os.environ.setdefault("CODEX_REPO_PATH", str(ROOT))
    _remove_hermes_environment()
    return loaded


def _remove_hermes_environment() -> None:
    """Fail closed if the local process inherited shared Hermes credentials."""

    dedicated_bot = os.environ.get("CODEX_DISCORD_BOT_TOKEN", "").strip()
    hermes_bot = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if dedicated_bot and hermes_bot and dedicated_bot == hermes_bot:
        raise RuntimeError("local Codex bot token matches the Hermes bot token")
    dedicated_worker = os.environ.get("CODEX_CHAT_WORKER_TOKEN", "").strip()
    technical_worker = os.environ.get("CODEX_WORKER_TOKEN", "").strip()
    if dedicated_worker and technical_worker and dedicated_worker == technical_worker:
        raise RuntimeError("local Chat Worker token matches the technical-worker token")
    os.environ.pop("DISCORD_BOT_TOKEN", None)
    os.environ.pop("CODEX_WORKER_TOKEN", None)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-local-bot")
    parser.add_argument(
        "--env-file",
        default=str(ROOT / ".env"),
        help="dotenv path; only dedicated Codex bot keys are loaded",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="check local configuration without connecting to Discord",
    )
    return parser


def _check() -> int:
    required = {
        "CODEX_DISCORD_BOT_TOKEN": bool(os.environ.get("CODEX_DISCORD_BOT_TOKEN", "").strip()),
        "CODEX_CHAT_WORKER_TOKEN": bool(os.environ.get("CODEX_CHAT_WORKER_TOKEN", "").strip()),
        "OPENAI_API_KEY": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
    }
    try:
        worker = worker_from_environment()
        codex_status = worker.status()
    except (ValueError, RuntimeError) as exc:
        codex_status = {"state": "unavailable", "message": str(exc)}
    restrictions = {
        "guild restriction": bool(os.environ.get("CODEX_DISCORD_GUILD_ID", "").strip()),
        "text channel restriction": bool(os.environ.get("CODEX_DISCORD_TEXT_CHANNEL_ID", "").strip()),
        "voice channel restriction": bool(os.environ.get("CODEX_DISCORD_VOICE_CHANNEL_ID", "").strip()),
    }
    openai_ready = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    print("codex-local-bot preflight")
    for key, present in required.items():
        print(f"{key}: {'present' if present else 'missing'}")
    print(f"Codex CLI: {codex_status['state']}")
    for label, present in restrictions.items():
        print(f"{label}: {'set' if present else 'missing'}")
    return 0 if all(required.values()) and codex_status["state"] == "ready" and all(restrictions.values()) else 2


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        load_local_environment(args.env_file)
        if args.check:
            return _check()
        # This entry point always owns a local loopback worker.  Do not let a
        # stale remote URL in .env redirect the local bot elsewhere.
        host = "127.0.0.1"
        port = int(os.environ.get("CODEX_CHAT_PORT", "8777"))
        os.environ["CODEX_CHAT_WORKER_URL"] = f"http://{host}:{port}"
        settings = CodexDiscordSettings.from_env()
        worker = worker_from_environment()
        server = ChatWorkerHTTPServer(
            worker,
            host,
            port,
            settings.chat_worker_token,
        )
    except (OSError, RuntimeError, ValueError, ImportError) as exc:
        raise SystemExit(f"codex-local-bot configuration error: {exc}") from None

    thread = threading.Thread(
        target=server.serve_forever,
        name="codex-chat-worker",
        daemon=True,
    )
    thread.start()
    try:
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
        bridge.run()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
