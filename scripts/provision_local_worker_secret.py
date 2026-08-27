from __future__ import annotations

import getpass
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"


def main() -> int:
    print("CODEX_WORKER_TOKEN is entered locally; it is never displayed or sent to Discord.")
    token = getpass.getpass("VPS CODEX_WORKER_TOKEN: ").strip()
    if not token:
        print("No token entered; nothing changed.")
        return 1
    existing = []
    if ENV_FILE.exists():
        existing = [
            line for line in ENV_FILE.read_text(encoding="utf-8").splitlines()
            if not line.strip().startswith("CODEX_WORKER_TOKEN=")
        ]
    existing.append(f"CODEX_WORKER_TOKEN={token}")
    ENV_FILE.write_text("\n".join(existing) + "\n", encoding="utf-8")
    try:
        os.chmod(ENV_FILE, 0o600)
    except OSError:
        pass
    print(f"Saved {ENV_FILE} without displaying the token.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
