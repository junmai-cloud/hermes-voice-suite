"""Small, dependency-free dotenv loader for local entry points.

The project deliberately does not depend on python-dotenv.  Entry points use
an explicit allow-list so a local Codex bot cannot accidentally import Hermes
or technical-worker credentials from the shared ``.env`` file.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from collections.abc import Collection


_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_dotenv_allowlisted(
    path: str | Path,
    *,
    allowed_keys: Collection[str],
    override: bool = False,
) -> set[str]:
    """Load only explicitly allowed keys and return the keys that were set.

    Existing process environment values win by default.  Values are never
    printed or returned; callers receive only key names for diagnostics.
    """

    dotenv_path = Path(path)
    if not dotenv_path.is_file():
        return set()
    allowed = set(allowed_keys)
    loaded: set[str] = set()
    for line_number, raw_line in enumerate(
        dotenv_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator or not _KEY_RE.fullmatch(key):
            raise ValueError(f"invalid .env assignment at line {line_number}")
        if key not in allowed or (key in os.environ and not override):
            continue
        try:
            parsed = shlex.split(raw_value, comments=True, posix=True)
        except ValueError as exc:
            raise ValueError(f"invalid .env value at line {line_number}") from exc
        os.environ[key] = " ".join(parsed) if parsed else ""
        loaded.add(key)
    return loaded
