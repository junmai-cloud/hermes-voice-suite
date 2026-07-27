import math
import os
import struct
import subprocess
import wave
from pathlib import Path

from voice_suite.podcast import PodcastProducer, remove_expired_audio


class FakeSynthesizer:
    def synthesize(self, text: str, output_path: Path) -> Path:
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
             "-i", "sine=frequency=440:duration=0.4", str(output_path)],
            check=True,
        )
        return output_path


def _tone(path: Path, frequency: int) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        frames = b"".join(
            struct.pack("<h", int(5000 * math.sin(2 * math.pi * frequency * i / 8000)))
            for i in range(8000 // 2)
        )
        handle.writeframes(frames)


def test_podcast_producer_mixes_voice_and_bgm(tmp_path):
    bgm = tmp_path / "bgm.wav"
    output = tmp_path / "podcast.mp3"
    _tone(bgm, 110)
    result = PodcastProducer(FakeSynthesizer()).produce("朝のブリーフィング", output, bgm_path=bgm)
    assert result == output
    assert output.exists()
    assert output.stat().st_size > 0


def test_podcast_producer_without_bgm_and_retention(tmp_path):
    output = tmp_path / "podcast.mp3"
    PodcastProducer(FakeSynthesizer()).produce("夕方のブリーフィング", output)
    assert output.exists()
    old = tmp_path / "old.mp3"
    old.write_bytes(b"old")
    os.utime(old, (0, 0))
    assert remove_expired_audio(tmp_path, now=25 * 3600) == 1
    assert not old.exists()
    assert output.exists()
