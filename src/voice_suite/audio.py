"""Audio encoding helpers to keep upstream speech traffic compact."""

from __future__ import annotations

import subprocess
from pathlib import Path


def pcm_to_webm_opus(
    pcm: bytes,
    output_path: Path,
    *,
    sample_rate: int = 48_000,
    bitrate: str = "24k",
) -> Path:
    """Encode signed 16-bit mono PCM to WebM/Opus for STT upload."""
    command = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-f", "s16le", "-ar", str(sample_rate), "-ac", "1", "-i", "pipe:0",
        "-c:a", "libopus", "-b:a", bitrate, "-f", "webm", str(output_path),
    ]
    result = subprocess.run(command, input=pcm, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace").strip() or "ffmpeg encoding failed")
    return output_path
