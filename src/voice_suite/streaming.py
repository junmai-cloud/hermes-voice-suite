"""Pycord streaming sink that emits completed PCM turns."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from .vad import EnergyVAD

TurnCallback = Callable[[int, bytes], Any | Awaitable[Any]]


class StreamingSink:
    """Feed decoded PCM frames into one VAD per Discord speaker.

    The class is intentionally duck-typed so its VAD logic is testable without
    connecting to Discord. ``as_pycord_sink`` returns the concrete Pycord sink.
    """

    def __init__(self, on_turn: TurnCallback, *, vad_factory=EnergyVAD, loop=None):
        self.on_turn = on_turn
        self.vad_factory = vad_factory
        self.loop = loop or asyncio.get_event_loop()
        self.vads: dict[int, EnergyVAD] = {}
        self.audio_data: dict[int, Any] = {}
        self.finished = False

    def write(self, data: bytes, user: int) -> None:
        if self.finished:
            return
        vad = self.vads.setdefault(user, self.vad_factory())
        for turn in vad.feed(data):
            self._dispatch(user, turn)

    def cleanup(self) -> None:
        self.finished = True
        for user, vad in self.vads.items():
            turn = vad.flush()
            if turn:
                self._dispatch(user, turn)

    def _dispatch(self, user: int, pcm: bytes) -> None:
        result = self.on_turn(user, pcm)
        if inspect.isawaitable(result):
            self.loop.create_task(result)

    @staticmethod
    def as_pycord_sink(on_turn: TurnCallback, *, vad_factory=EnergyVAD, loop=None):
        """Create a Pycord Sink subclass when the optional voice dependency exists."""
        try:
            from discord.sinks import Sink
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install the voice extra first") from exc

        bridge = StreamingSink(on_turn, vad_factory=vad_factory, loop=loop)

        class PycordStreamingSink(Sink):
            def __init__(self):
                super().__init__()
                self.bridge = bridge

            def write(self, data, user):
                self.bridge.write(data, user)

            def cleanup(self):
                self.bridge.cleanup()
                super().cleanup()

        return PycordStreamingSink()
