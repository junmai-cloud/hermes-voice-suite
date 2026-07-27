from voice_suite.discord_bridge import VoiceBridge, VoiceBotSettings


class FakeVoiceClient:
    def __init__(self):
        self.playing = True
        self.stopped = False

    def is_playing(self):
        return self.playing

    def stop(self):
        self.stopped = True
        self.playing = False


def test_voice_activity_interrupts_playback():
    bridge = VoiceBridge(
        VoiceBotSettings("token"),
        transcriber=lambda path: "",
        synthesizer=lambda text, path: path,
    )
    client = FakeVoiceClient()
    bridge.voice_client = client
    bridge._interrupt_playback()
    assert client.stopped is True
    assert client.playing is False
