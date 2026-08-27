import asyncio
import struct
import threading
import time

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


def test_streaming_sink_normalises_discord_user_objects_and_stereo_pcm():
    received = []
    loop = asyncio.new_event_loop()
    sink = StreamingSink(
        lambda user, audio: received.append((user, audio)),
        vad_factory=lambda: EnergyVAD(threshold=100, trailing_silence_ms=40),
        loop=loop,
        input_channels=2,
    )

    class User:
        id = 9

    stereo_samples = 48_000 * 20 // 1000
    stereo = struct.pack(
        "<" + "hh" * stereo_samples,
        *([1000, 800] * stereo_samples),
    )
    sink.write(stereo * 2, User())
    sink.write(bytes(len(stereo) * 2), User())

    assert [user for user, _ in received] == [9]
    loop.close()


def test_streaming_sink_moves_packet_router_work_to_running_loop():
    received = []
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    def run_loop():
        asyncio.set_event_loop(loop)
        loop.call_soon(ready.set)
        loop.run_forever()

    thread = threading.Thread(target=run_loop)
    thread.start()
    assert ready.wait(1)
    sink = StreamingSink(
        lambda user, audio: received.append(user),
        vad_factory=lambda: EnergyVAD(threshold=100, trailing_silence_ms=40),
        loop=loop,
    )
    sink.write(pcm(1000, 2), 11)
    sink.write(pcm(0, 2), 11)
    deadline = time.monotonic() + 1
    while not received and time.monotonic() < deadline:
        time.sleep(0.01)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=1)
    loop.close()

    assert received == [11]
