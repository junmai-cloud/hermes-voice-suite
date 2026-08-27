from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
RETRY_SECONDS = int(os.environ.get("CODEX_LOCAL_BOT_RETRY_SECONDS", "30"))
REQUIRED = ("CODEX_DISCORD_BOT_TOKEN", "CODEX_CHAT_WORKER_TOKEN", "OPENAI_API_KEY")


def secrets_ready() -> bool:
    if not ENV_FILE.exists():
        return False
    values = {}
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return all(values.get(key) for key in REQUIRED)


def main() -> int:
    print("local Codex JUNMAI bot supervisor active", flush=True)
    while True:
        if not secrets_ready():
            print("waiting for local Codex bot credentials", flush=True)
            time.sleep(RETRY_SECONDS)
            continue
        print("starting local Codex JUNMAI bot", flush=True)
        result = subprocess.run(
            [os.environ.get("PYTHON", "python"), "-m", "voice_suite.codex_local_cli"],
            cwd=ROOT,
            check=False,
        )
        print(f"local bot exited code={result.returncode}; retrying", flush=True)
        time.sleep(RETRY_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
