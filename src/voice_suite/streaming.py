"""Pycord streaming sink that emits completed PCM turns."""

from __future__ import annotations

import asyncio
import array
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
        input_channels: int = 1,
    ):
        self.on_turn = on_turn
        self.on_head = on_head
        self.head_ms = head_ms
        self.vad_factory = vad_factory
        self.loop = loop or asyncio.get_event_loop()
        self.input_channels = max(1, int(input_channels))
        self.vads: dict[int, EnergyVAD] = {}
        self.audio_data: dict[int, Any] = {}
        self._head_emitted: set[int] = set()
        self.finished = False

    def write(self, data: bytes, user: int) -> None:
        """Accept one Pycord packet, moving processing onto the event loop.

        Pycord's PacketRouter calls ``Sink.write`` from its own worker thread.
        VAD state and async callbacks must therefore never be touched directly
        from that thread.
        """
        user_id = self._normalise_user(user)
        if user_id is None:
            return
        pcm = self._to_mono(bytes(data), self.input_channels)
        self._on_loop(self._write_on_loop, pcm, user_id)

    def _write_on_loop(self, data: bytes, user: int) -> None:
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
        """Flush all partial turns on the event loop in packet order."""
        self._on_loop(self._cleanup_on_loop)

    def _cleanup_on_loop(self) -> None:
        if self.finished:
            return
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
            if self.loop.is_running():
                self.loop.create_task(result)
            else:
                result.close()

    def _on_loop(self, callback, *args) -> None:
        """Run immediately on the loop or enqueue safely from another thread."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if not self.loop.is_running() or current_loop is self.loop:
            callback(*args)
            return
        try:
            self.loop.call_soon_threadsafe(callback, *args)
        except RuntimeError:
            # The process is shutting down; no new audio should be dispatched.
            return

    @staticmethod
    def _normalise_user(user: Any) -> int | None:
        value = getattr(user, "id", user)
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_mono(pcm: bytes, channels: int) -> bytes:
        """Downmix Pycord's 48 kHz stereo s16le output for the mono VAD."""
        if channels <= 1:
            return pcm
        sample_bytes = len(pcm) - (len(pcm) % 2)
        samples = array.array("h")
        samples.frombytes(pcm[:sample_bytes])
        if len(samples) < channels:
            return b""
        mono = array.array("h")
        for index in range(0, len(samples) - channels + 1, channels):
            total = sum(samples[index + offset] for offset in range(channels))
            mono.append(max(-32768, min(32767, total // channels)))
        return mono.tobytes()

    @staticmethod
    def as_pycord_sink(
        on_turn: TurnCallback,
        *,
        on_head: HeadCallback | None = None,
        head_ms: int = 2_000,
        vad_factory=EnergyVAD,
        loop=None,
        input_channels: int = 2,
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
            input_channels=input_channels,
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
