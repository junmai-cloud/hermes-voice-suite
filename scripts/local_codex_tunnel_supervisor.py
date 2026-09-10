from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SSH_CONFIG = os.environ.get("CODEX_SSH_CONFIG", str(ROOT / "codex-ssh-config"))
SSH_TARGET = os.environ.get("CODEX_SSH_TARGET", "hub-vps")
LOCAL_HOST = os.environ.get("CODEX_LOCAL_WORKER_HOST", "127.0.0.1")
LOCAL_PORT = int(os.environ.get("CODEX_LOCAL_WORKER_PORT", "8767"))
REMOTE_PORT = int(os.environ.get("CODEX_REMOTE_WORKER_PORT", "8767"))
RETRY_SECONDS = int(os.environ.get("CODEX_TUNNEL_RETRY_SECONDS", "60"))
MAX_RETRY_SECONDS = int(os.environ.get("CODEX_TUNNEL_MAX_RETRY_SECONDS", "3600"))


def worker_ready() -> bool:
    try:
        with urlopen(f"http://{LOCAL_HOST}:{LOCAL_PORT}/health", timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def ssh_config_ready() -> bool:
    """Validate the SSH configuration without opening a network connection."""
    if not Path(SSH_CONFIG).is_file():
        return False
    result = subprocess.run(
        [
            "ssh",
            "-F",
            SSH_CONFIG,
            "-o",
            "BatchMode=yes",
            "-G",
            SSH_TARGET,
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def retry_delay(failures: int) -> int:
    """Back off failed authentication paths so fail2ban is not hammered."""
    return min(RETRY_SECONDS * (2 ** max(failures - 1, 0)), MAX_RETRY_SECONDS)


def main() -> int:
    print(f"tunnel supervisor active remote=127.0.0.1:{REMOTE_PORT}", flush=True)
    failures = 0
    while True:
        if not worker_ready():
            print("waiting for local worker health", flush=True)
            time.sleep(RETRY_SECONDS)
            continue
        if not ssh_config_ready():
            print("waiting for valid SSH config; no connection attempted", flush=True)
            time.sleep(MAX_RETRY_SECONDS)
            continue
        command = [
            "ssh",
            "-F",
            SSH_CONFIG,
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "ConnectTimeout=8",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
            "-R",
            f"127.0.0.1:{REMOTE_PORT}:{LOCAL_HOST}:{LOCAL_PORT}",
            SSH_TARGET,
            "-N",
        ]
        print("reverse tunnel starting", flush=True)
        started = time.monotonic()
        result = subprocess.run(command, cwd=ROOT, check=False)
        if time.monotonic() - started >= 300:
            failures = 0
        failures += 1
        delay = retry_delay(failures)
        print(f"reverse tunnel exited code={result.returncode}; retrying in {delay}s", flush=True)
        time.sleep(delay)


if __name__ == "__main__":
    raise SystemExit(main())
