from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
HOST = os.environ.get("CODEX_LOCAL_WORKER_HOST", "127.0.0.1")
PORT = int(os.environ.get("CODEX_LOCAL_WORKER_PORT", "8767"))
WORKER_ID = os.environ.get("CODEX_LOCAL_WORKER_ID", "local-codex-burst-1")
RETRY_SECONDS = int(os.environ.get("CODEX_LOCAL_WORKER_RETRY_SECONDS", "30"))


def load_token() -> str | None:
    if not ENV_FILE.exists():
        return None
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "CODEX_WORKER_TOKEN":
            value = value.strip().strip('"').strip("'")
            return value or None
    return None


def port_available() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((HOST, PORT)) != 0


def run_worker(token: str) -> int:
    env = os.environ.copy()
    env["CODEX_WORKER_TOKEN"] = token
    env.setdefault("CODEX_REPO_PATH", str(ROOT))
    command = [
        sys.executable,
        "-m",
        "voice_suite.technical_cli",
        "worker",
        "--worker-id",
        WORKER_ID,
        "--host",
        HOST,
        "--port",
        str(PORT),
        "--repo",
        str(ROOT),
    ]
    print(f"worker starting id={WORKER_ID} host={HOST} port={PORT}", flush=True)
    completed = subprocess.run(command, cwd=ROOT, env=env)
    return completed.returncode


def main() -> int:
    print(f"supervisor active root={ROOT} port={PORT}", flush=True)
    while True:
        token = load_token()
        if token is None:
            print("waiting for CODEX_WORKER_TOKEN in .env", flush=True)
            time.sleep(RETRY_SECONDS)
            continue
        if not port_available():
            print(f"port {PORT} is occupied; waiting without touching existing service", flush=True)
            time.sleep(RETRY_SECONDS)
            continue
        code = run_worker(token)
        print(f"worker exited code={code}; retrying", flush=True)
        time.sleep(RETRY_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
