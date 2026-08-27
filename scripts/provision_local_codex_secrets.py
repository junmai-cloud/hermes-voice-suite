"""Provision local-only Codex JUNMAI credentials without displaying them."""

from __future__ import annotations

import getpass
import secrets
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"


def _read_assignments() -> list[str]:
    if not ENV_FILE.exists():
        return []
    return ENV_FILE.read_text(encoding="utf-8").splitlines()


def _set_value(lines: list[str], key: str, value: str) -> list[str]:
    prefix = f"{key}="
    replaced = False
    result: list[str] = []
    for line in lines:
        if line.strip().startswith(prefix):
            if not replaced:
                result.append(f"{prefix}{value}")
                replaced = True
            continue
        result.append(line)
    if not replaced:
        result.append(f"{prefix}{value}")
    return result


def main() -> int:
    print("Local Codex JUNMAI credentials are written to .env; values are not displayed.")
    bot_token = getpass.getpass("CODEX_DISCORD_BOT_TOKEN: ").strip()
    if not bot_token:
        print("No Discord bot token entered; nothing changed.")
        return 1
    chat_token = secrets.token_urlsafe(32)
    lines = _read_assignments()
    lines = _set_value(lines, "CODEX_DISCORD_BOT_TOKEN", bot_token)
    lines = _set_value(lines, "CODEX_CHAT_WORKER_TOKEN", chat_token)
    ENV_FILE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    try:
        ENV_FILE.chmod(0o600)
    except OSError:
        pass
    print(f"Saved {ENV_FILE} with a generated local Chat Worker token.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
