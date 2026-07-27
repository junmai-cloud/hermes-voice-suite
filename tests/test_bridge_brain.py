from voice_suite.discord_bridge import VoiceBridge, VoiceBotSettings
from voice_suite.meeting import MeetingOrchestrator


class FakeBrain:
    def answer(self, text: str) -> str:
        return f"整理した回答: {text}"


class FakeTranscriber:
    def transcribe(self, path):
        return "今日の会議を始めよう"


class FakeSynthesizer:
    def synthesize(self, text, output_path):
        output_path.write_bytes(b"audio")
        return output_path


def test_bridge_routes_text_to_brain():
    bridge = VoiceBridge(
        VoiceBotSettings("token"),
        transcriber=FakeTranscriber(),
        synthesizer=FakeSynthesizer(),
        brain=FakeBrain(),
        meeting=MeetingOrchestrator(),
    )
    assert bridge._reply_for("今日の予定") == "整理した回答: 今日の予定"
