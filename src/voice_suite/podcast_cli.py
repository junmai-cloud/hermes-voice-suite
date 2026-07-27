"""CLI entry point for producing a retained podcast audio file."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .adapters import OpenAISynthesizer
from .podcast import PodcastProducer, remove_expired_audio


class EdgeJapaneseSynthesizer:
    def __init__(self, voice: str = "ja-JP-KeitaNeural") -> None:
        self.voice = voice
        self.command = shutil.which("edge-tts") or "/usr/local/lib/hermes-agent/venv/bin/edge-tts"

    def synthesize(self, text: str, output_path: Path) -> Path:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt") as source:
            source.write(text)
            source.flush()
            subprocess.run(
                [self.command, "--voice", self.voice, "--file", source.name, "--write-media", str(output_path)],
                check=True,
            )
        return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a Japanese briefing podcast")
    parser.add_argument("--text-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bgm", type=Path)
    parser.add_argument("--voice", default="ja-JP-KeitaNeural")
    parser.add_argument("--provider", choices=("edge", "openai"), default="edge")
    parser.add_argument("--retention-hours", type=float, default=24.0)
    args = parser.parse_args(argv)

    text = args.text_file.read_text(encoding="utf-8") if args.text_file else sys.stdin.read()
    if not text.strip():
        parser.error("podcast text is empty")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    removed = remove_expired_audio(args.output.parent, max_age_hours=args.retention_hours)
    PodcastProducer(
        EdgeJapaneseSynthesizer(args.voice) if args.provider == "edge" else OpenAISynthesizer(voice=args.voice)
    ).produce(text, args.output, bgm_path=args.bgm)
    print(f"podcast_created={args.output}")
    print(f"expired_audio_removed={removed}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
