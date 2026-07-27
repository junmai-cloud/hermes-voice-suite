"""Small, provider-independent voice activity and barge-in primitives."""

from __future__ import annotations

import array
from dataclasses import dataclass, field


@dataclass
class EnergyVAD:
    """Segment signed 16-bit mono PCM using simple RMS energy."""

    threshold: int = 500
    trailing_silence_ms: int = 650
    max_turn_ms: int = 20_000
    frame_ms: int = 20
    sample_rate: int = 48_000
    _buffer: bytearray = field(default_factory=bytearray, init=False)
    _turn: bytearray = field(default_factory=bytearray, init=False)
    _speaking: bool = field(default=False, init=False)
    _silence_ms: int = field(default=0, init=False)
    _turn_ms: int = field(default=0, init=False)

    def feed(self, pcm: bytes) -> list[bytes]:
        """Feed PCM frames and return zero or more completed turns."""
        self._buffer.extend(pcm)
        frame_bytes = self.sample_rate * self.frame_ms // 1000 * 2
        completed: list[bytes] = []
        while len(self._buffer) >= frame_bytes:
            frame = bytes(self._buffer[:frame_bytes])
            del self._buffer[:frame_bytes]
            energy = self._rms(frame)
            voiced = energy >= self.threshold
            if voiced and not self._speaking:
                self._speaking = True
                self._turn.clear()
                self._turn_ms = 0
                self._silence_ms = 0
            if self._speaking:
                self._turn.extend(frame)
                self._turn_ms += self.frame_ms
                self._silence_ms = 0 if voiced else self._silence_ms + self.frame_ms
                if self._silence_ms >= self.trailing_silence_ms or self._turn_ms >= self.max_turn_ms:
                    completed.append(self._finish())
        return completed

    def flush(self) -> bytes | None:
        """Finish a partial turn, useful when recording stops."""
        return self._finish() if self._speaking and self._turn else None

    @staticmethod
    def _rms(frame: bytes) -> int:
        samples = array.array("h")
        samples.frombytes(frame[: len(frame) - len(frame) % 2])
        if not samples:
            return 0
        return int((sum(sample * sample for sample in samples) / len(samples)) ** 0.5)

    def _finish(self) -> bytes:
        result = bytes(self._turn)
        self._turn.clear()
        self._speaking = False
        self._silence_ms = 0
        self._turn_ms = 0
        return result


@dataclass
class BargeInController:
    """Stop playback as soon as a new voiced turn begins."""

    playing: bool = False
    interrupted: bool = field(default=False, init=False)

    def start_playback(self) -> None:
        self.playing = True
        self.interrupted = False

    def on_voice_activity(self) -> bool:
        """Return True when the current playback must be stopped."""
        if not self.playing:
            return False
        self.playing = False
        self.interrupted = True
        return True

    def finish_playback(self) -> None:
        self.playing = False
