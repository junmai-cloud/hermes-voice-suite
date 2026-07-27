"""Podcast audio production helpers with bounded retention."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Protocol


class Synthesizer(Protocol):
    def synthesize(self, text: str, output_path: Path) -> Path: ...


class PodcastProducer:
    """Render narration and optionally mix a low-volume music bed."""

    def __init__(self, synthesizer: Synthesizer, *, bgm_volume: float = 0.08) -> None:
        if not 0.0 <= bgm_volume <= 1.0:
            raise ValueError("bgm_volume must be between 0 and 1")
        self.synthesizer = synthesizer
        self.bgm_volume = bgm_volume

    def produce(self, text: str, output_path: Path, *, bgm_path: Path | None = None) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="hermes-podcast-") as workdir:
            narration = Path(workdir) / "narration.mp3"
            self.synthesizer.synthesize(text, narration)
            if bgm_path is None:
                shutil.copyfile(narration, output_path)
            else:
                self._mix(narration, bgm_path, output_path)
        return output_path

    def _mix(self, narration: Path, bgm: Path, output: Path) -> None:
        filter_graph = (
            f"[1:a]volume={self.bgm_volume:.3f}[music];"
            "[0:a][music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]"
        )
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(narration), "-stream_loop", "-1", "-i", str(bgm),
                "-filter_complex", filter_graph, "-map", "[a]",
                "-c:a", "libmp3lame", "-q:a", "4", str(output),
            ],
            check=True,
        )


def remove_expired_audio(directory: Path, *, max_age_hours: float = 24.0, now: float | None = None) -> int:
    """Remove generated audio files older than the retention window."""
    if max_age_hours <= 0:
        raise ValueError("max_age_hours must be positive")
    cutoff = (time.time() if now is None else now) - max_age_hours * 3600
    removed = 0
    for path in directory.glob("*.mp3"):
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()
            removed += 1
    return removed
