import struct

from voice_suite.vad import BargeInController, EnergyVAD


def pcm(value: int, frames: int, sample_rate: int = 48_000, frame_ms: int = 20) -> bytes:
    count = sample_rate * frame_ms // 1000 * frames
    return struct.pack("<" + "h" * count, *([value] * count))


def test_vad_returns_turn_after_trailing_silence():
    vad = EnergyVAD(threshold=100, trailing_silence_ms=60)
    assert vad.feed(pcm(1000, 3)) == []
    turns = vad.feed(pcm(0, 3))
    assert len(turns) == 1
    assert len(turns[0]) > 0


def test_vad_ignores_silence_until_voice():
    vad = EnergyVAD(threshold=100, trailing_silence_ms=40)
    assert vad.feed(pcm(0, 10)) == []


def test_barge_in_stops_playback_once():
    controller = BargeInController()
    controller.start_playback()
    assert controller.on_voice_activity() is True
    assert controller.on_voice_activity() is False
    assert controller.interrupted is True
