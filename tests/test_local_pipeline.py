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


def test_voice_turn_uses_one_head_and_one_tail_stt_without_full_repeat():
    class CountingTranscriber:
        def __init__(self):
            self.calls = []

        def transcribe(self, path: Path) -> str:
            self.calls.append(path.name)
            return "結論" if len(self.calls) == 1 else "を説明します"

    async def run():
        transcriber = CountingTranscriber()
        bridge = VoiceBridge(
            VoiceBotSettings("local-test"),
            transcriber=transcriber,
            synthesizer=FakeSynthesizer(),
            brain=FakeBrain(),
        )
        full_pcm = b"\x01\x00" * (48_000 * 3)
        head_pcm = full_pcm[: 48_000 * 2]
        bridge._schedule_voice_head(42, head_pcm)
        await bridge._on_pcm_turn(42, full_pcm)
        assert len(transcriber.calls) == 2

    asyncio.run(run())
