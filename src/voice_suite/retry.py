"""Bounded retries for transient provider failures."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar


T = TypeVar("T")


def retry_call(fn: Callable[[], T], *, retries: int = 1, delay_seconds: float = 0.5) -> T:
    """Call a provider with a small, explicit retry budget."""
    attempts = 0
    while True:
        try:
            return fn()
        except Exception:
            if attempts >= retries:
                raise
            attempts += 1
            if delay_seconds > 0:
                time.sleep(delay_seconds)
