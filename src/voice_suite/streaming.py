"""Pycord streaming sink that emits completed PCM turns."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from .vad import EnergyVAD

TurnCallback = Callable[[int, bytes], Any | Awaitable[Any]]
HeadCallback = Callable[[int, bytes], Any | Awaitable[Any]]


class StreamingSink:
    """Feed decoded PCM frames into one VAD per Discord speaker.

    The class is intentionally duck-typed so its VAD logic is testable without
    connecting to Discord. ``as_pycord_sink`` returns the concrete Pycord sink.
    """

    def __init__(
        self,
        on_turn: TurnCallback,
        *,
        on_head: HeadCallback | None = None,
        head_ms: int = 2_000,
        vad_factory=EnergyVAD,
        loop=None,
    ):
        self.on_turn = on_turn
        self.on_head = on_head
        self.head_ms = head_ms
        self.vad_factory = vad_factory
        self.loop = loop or asyncio.get_event_loop()
        self.vads: dict[int, EnergyVAD] = {}
        self.audio_data: dict[int, Any] = {}
        self._head_emitted: set[int] = set()
        self.finished = False

    def write(self, data: bytes, user: int) -> None:
        if self.finished:
            return
        vad = self.vads.setdefault(user, self.vad_factory())
        completed = vad.feed(data)
        if self.on_head and user not in self._head_emitted:
            preview = vad.preview(self.head_ms)
            if preview:
                self._head_emitted.add(user)
                self._dispatch(self.on_head, user, preview)
        for turn in completed:
            # A turn can cross the head threshold and finish in the same
            # incoming packet.  In that case the active VAD no longer has a
            # snapshot, so derive it from the completed turn.
            if self.on_head and user not in self._head_emitted:
                bytes_per_ms = 48_000 * 2 // 1000
                head_bytes = bytes_per_ms * self.head_ms
                if len(turn) >= head_bytes:
                    self._head_emitted.add(user)
                    self._dispatch(self.on_head, user, turn[:head_bytes])
            self._dispatch(self.on_turn, user, turn)
            self._head_emitted.discard(user)

    def cleanup(self) -> None:
        self.finished = True
        for user, vad in self.vads.items():
            turn = vad.flush()
            if turn:
                if self.on_head and user not in self._head_emitted:
                    bytes_per_ms = 48_000 * 2 // 1000
                    head_bytes = bytes_per_ms * self.head_ms
                    if len(turn) >= head_bytes:
                        self._head_emitted.add(user)
                        self._dispatch(self.on_head, user, turn[:head_bytes])
                self._dispatch(self.on_turn, user, turn)
                self._head_emitted.discard(user)

    def _dispatch(self, callback, user: int, pcm: bytes) -> None:
        result = callback(user, pcm)
        if inspect.isawaitable(result):
            self.loop.create_task(result)

    @staticmethod
    def as_pycord_sink(
        on_turn: TurnCallback,
        *,
        on_head: HeadCallback | None = None,
        head_ms: int = 2_000,
        vad_factory=EnergyVAD,
        loop=None,
    ):
        """Create a Pycord Sink subclass when the optional voice dependency exists."""
        try:
            from discord.sinks import Sink
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install the voice extra first") from exc

        bridge = StreamingSink(
            on_turn,
            on_head=on_head,
            head_ms=head_ms,
            vad_factory=vad_factory,
            loop=loop,
        )

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
