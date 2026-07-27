import asyncio
from pathlib import Path

from voice_suite.discord_bridge import VoiceBridge, VoiceBotSettings


class FakeVoiceClient:
    def __init__(self):
        self.played = []

    def is_playing(self):
        return False

    def play(self, source, after):
        self.played.append(source)
        after(None)


class FakeTranscriber:
    def transcribe(self, path: Path) -> str:
        assert path.suffix == ".webm"
        assert path.stat().st_size > 0
        return "今日の会議を始めよう"


class FakeBrain:
    def answer(self, text: str) -> str:
        return "今日は最初に重要な予定を確認しましょう。"


class FakeSynthesizer:
    def synthesize(self, text: str, output_path: Path) -> Path:
        assert text.startswith(("今日は", "すみません"))
        output_path.write_bytes(b"fake-mp3")
        return output_path


def test_local_voice_turn_runs_full_pipeline():
    bridge = VoiceBridge(
        VoiceBotSettings("local-test"),
        transcriber=FakeTranscriber(),
        synthesizer=FakeSynthesizer(),
        brain=FakeBrain(),
    )
    client = FakeVoiceClient()
    bridge.voice_client = client
    asyncio.run(bridge._on_pcm_turn(42, b"\x01\x00" * 48_000))
    assert len(client.played) == 1
    assert bridge.metrics.turns == 1
    assert bridge.metrics.stt_bytes > 0
    assert bridge.metrics.snapshot()["stt_bytes"] < 10_000


def test_local_voice_turn_counts_provider_failure_without_raising():
    class BrokenTranscriber:
        def transcribe(self, path: Path) -> str:
            raise RuntimeError("provider unavailable")

    bridge = VoiceBridge(
        VoiceBotSettings("local-test"),
        transcriber=BrokenTranscriber(),
        synthesizer=FakeSynthesizer(),
        brain=FakeBrain(),
    )
    asyncio.run(bridge._on_pcm_turn(42, b"\x01\x00" * 48_000))
    assert bridge.metrics.errors == 1


def test_empty_transcription_gets_spoken_clarification():
    class EmptyTranscriber:
        def transcribe(self, path: Path) -> str:
            return ""

    bridge = VoiceBridge(
        VoiceBotSettings("local-test"),
        transcriber=EmptyTranscriber(),
        synthesizer=FakeSynthesizer(),
        brain=FakeBrain(),
    )
    client = FakeVoiceClient()
    bridge.voice_client = client
    asyncio.run(bridge._on_pcm_turn(42, b"\x01\x00" * 48_000))
    assert len(client.played) == 1
    assert bridge.metrics.turns == 1
    assert bridge.metrics.clarifications == 1


def test_disallowed_user_audio_is_ignored():
    bridge = VoiceBridge(
        VoiceBotSettings("local-test", allowed_user_id=7),
        transcriber=FakeTranscriber(),
        synthesizer=FakeSynthesizer(),
        brain=FakeBrain(),
    )
    asyncio.run(bridge._on_pcm_turn(42, b"\x01\x00" * 48_000))
    assert bridge.metrics.turns == 0
