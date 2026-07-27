import struct
from pathlib import Path

from voice_suite.audio import pcm_to_webm_opus


def test_pcm_to_webm_opus_reduces_raw_audio_size(tmp_path: Path):
    pcm = struct.pack("<" + "h" * (48_000 * 3), *([1000] * (48_000 * 3)))
    output = pcm_to_webm_opus(pcm, tmp_path / "turn.webm")
    assert output.exists()
    assert output.stat().st_size < len(pcm) / 10
