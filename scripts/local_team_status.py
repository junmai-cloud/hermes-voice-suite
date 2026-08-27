from __future__ import annotations

import os
import socket
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
PORT = int(os.environ.get("CODEX_LOCAL_WORKER_PORT", "8767"))


def main() -> int:
    token_set = False
    if ENV_FILE.exists():
        token_set = any(
            line.strip().startswith("CODEX_WORKER_TOKEN=")
            and bool(line.split("=", 1)[1].strip().strip('"').strip("'"))
            for line in ENV_FILE.read_text(encoding="utf-8").splitlines()
        )
    health = False
    try:
        with urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as response:
            health = response.status == 200
    except Exception:
        pass
    ssh_config = ROOT / "codex-ssh-config"
    print(f"env_file={'present' if ENV_FILE.exists() else 'missing'}")
    print(f"token={'set' if token_set else 'missing'}")
    print(f"local_worker_health={'ok' if health else 'waiting'}")
    print(f"ssh_config={'present' if ssh_config.exists() else 'missing'}")
    return 0 if token_set and health else 1


if __name__ == "__main__":
    raise SystemExit(main())
