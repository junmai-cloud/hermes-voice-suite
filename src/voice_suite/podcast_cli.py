"""CLI entry point for producing a retained podcast audio file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .adapters import OpenAISynthesizer
from .podcast import PodcastProducer, remove_expired_audio


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a Japanese briefing podcast")
    parser.add_argument("--text-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bgm", type=Path)
    parser.add_argument("--voice", default="alloy")
    parser.add_argument("--retention-hours", type=float, default=24.0)
    args = parser.parse_args(argv)

    text = args.text_file.read_text(encoding="utf-8") if args.text_file else sys.stdin.read()
    if not text.strip():
        parser.error("podcast text is empty")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    removed = remove_expired_audio(args.output.parent, max_age_hours=args.retention_hours)
    PodcastProducer(OpenAISynthesizer(voice=args.voice)).produce(
        text, args.output, bgm_path=args.bgm
    )
    print(f"podcast_created={args.output}")
    print(f"expired_audio_removed={removed}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
