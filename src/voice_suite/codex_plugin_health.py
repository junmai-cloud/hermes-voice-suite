"""Secret-free installation checks for Codex plugins.

Installation is deliberately reported separately from authentication and live
API readiness.  A package being present must never be treated as proof that an
integration works.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class PluginHealth:
    plugin: str
    installation: str
    enabled: bool
    version: str | None
    authentication: str = "UNVERIFIED"
    live_api: str = "UNVERIFIED"
    ready: bool = False
    next_action: str = "authenticate_in_codex_app_then_run_live_read"


def parse_plugin_list(output: str, plugin: str) -> PluginHealth:
    prefix = f"{plugin}@"
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line.startswith(prefix):
            continue
        columns = re.split(r"\s{2,}", line)
        enabled = "installed, enabled" in line
        installed = "installed" in line and "not installed" not in line
        version = columns[2] if enabled and len(columns) > 2 else None
        return PluginHealth(
            plugin=plugin,
            installation="INSTALLED" if installed else "NOT_INSTALLED",
            enabled=enabled,
            version=version,
            next_action=(
                "authenticate_in_codex_app_then_run_live_read"
                if enabled
                else "install_and_enable_plugin"
            ),
        )
    return PluginHealth(
        plugin=plugin,
        installation="NOT_FOUND",
        enabled=False,
        version=None,
        next_action="add_marketplace_or_install_plugin",
    )


def find_codex() -> str:
    configured = os.environ.get("CODEX_BIN")
    candidates = [configured, shutil.which("codex"), "/opt/codex/bin/codex"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise FileNotFoundError("Codex CLI was not found")


def check_plugin(plugin: str, *, command: Sequence[str] | None = None) -> PluginHealth:
    argv = list(command or (find_codex(), "plugin", "list"))
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"codex plugin list failed with exit code {result.returncode}")
    return parse_plugin_list(result.stdout, plugin)


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Check Codex plugin installation without secrets")
    parser.add_argument("plugin")
    args = parser.parse_args(argv)
    health = check_plugin(args.plugin)
    print(json.dumps(asdict(health), ensure_ascii=False, sort_keys=True))
    # Installed is not ready: OAuth and a live read remain mandatory.
    return 3 if health.enabled else 2


if __name__ == "__main__":
    raise SystemExit(main())
