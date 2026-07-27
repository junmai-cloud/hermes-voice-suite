"""Provider adapters for speech and the Hermes conversation brain.

All network clients are optional and injected/configured at runtime. This keeps
unit tests offline and prevents credentials from entering the repository.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Protocol


class Brain(Protocol):
    def answer(self, text: str) -> str: ...


class HermesCliBrain:
    """Use the installed Hermes CLI as the conversation brain.

    A future long-lived session transport can replace this without changing the
    Discord bridge or the meeting policy.
    """

    def __init__(self, *, command: str = "hermes", timeout: int = 90) -> None:
        self.command = command
        self.timeout = timeout

    def answer(self, text: str) -> str:
        result = subprocess.run(
            [self.command, "chat", "-q", text, "-Q", "--source", "tool"],
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Hermes CLI failed")
        return result.stdout.strip()


class OpenAITranscriber:
    """OpenAI Audio Transcriptions adapter; requires OPENAI_API_KEY."""

    def __init__(self, *, model: str = "gpt-4o-mini-transcribe") -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install the voice extra first") from exc
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.model = model

    def transcribe(self, wav_path: Path) -> str:
        with wav_path.open("rb") as audio:
            result = self.client.audio.transcriptions.create(model=self.model, file=audio)
        return result.text.strip()


class OpenAISynthesizer:
    """OpenAI speech adapter; requires OPENAI_API_KEY."""

    def __init__(self, *, model: str = "gpt-4o-mini-tts", voice: str = "alloy") -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install the voice extra first") from exc
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.model = model
        self.voice = voice

    def synthesize(self, text: str, output_path: Path) -> Path:
        with self.client.audio.speech.with_streaming_response.create(
            model=self.model,
            voice=self.voice,
            input=text,
            response_format="mp3",
        ) as response:
            response.stream_to_file(output_path)
        return output_path
