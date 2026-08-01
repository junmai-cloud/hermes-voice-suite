import asyncio
import struct

from voice_suite.streaming import StreamingSink
from voice_suite.vad import EnergyVAD


def pcm(value: int, frames: int) -> bytes:
    count = 48_000 * 20 // 1000 * frames
    return struct.pack("<" + "h" * count, *([value] * count))


def test_streaming_sink_emits_turn_per_user():
    received = []
    loop = asyncio.new_event_loop()
    sink = StreamingSink(
        lambda user, audio: received.append((user, audio)),
        vad_factory=lambda: EnergyVAD(threshold=100, trailing_silence_ms=40),
        loop=loop,
    )
    sink.write(pcm(1000, 2), 7)
    sink.write(pcm(0, 2), 7)
    assert len(received) == 1
    assert received[0][0] == 7
    loop.close()


def test_streaming_sink_flushes_on_cleanup():
    received = []
    loop = asyncio.new_event_loop()
    sink = StreamingSink(
        lambda user, audio: received.append(user),
        vad_factory=lambda: EnergyVAD(threshold=100, trailing_silence_ms=1000),
        loop=loop,
    )
    sink.write(pcm(1000, 1), 3)
    sink.cleanup()
    assert received == [3]
    loop.close()


def test_streaming_sink_emits_one_two_second_head_then_one_turn():
    heads = []
    turns = []
    loop = asyncio.new_event_loop()
    sink = StreamingSink(
        lambda user, audio: turns.append((user, audio)),
        on_head=lambda user, audio: heads.append((user, audio)),
        head_ms=2_000,
        vad_factory=lambda: EnergyVAD(threshold=100, trailing_silence_ms=40),
        loop=loop,
    )
    sink.write(pcm(1000, 100), 7)  # exactly two seconds of speech
    sink.write(pcm(1000, 10), 7)
    sink.write(pcm(0, 2), 7)
    assert [user for user, _ in heads] == [7]
    assert len(heads[0][1]) == len(pcm(1000, 100))
    assert [user for user, _ in turns] == [7]
    loop.close()
