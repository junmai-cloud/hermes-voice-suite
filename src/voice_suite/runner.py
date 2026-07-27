"""Production-style entry point for the Discord voice bot."""

from .adapters import HermesCliBrain, OpenAISynthesizer, OpenAITranscriber
from .discord_bridge import VoiceBridge, VoiceBotSettings


def main() -> None:
    try:
        settings = VoiceBotSettings.from_env()
        bridge = VoiceBridge(
            settings,
            transcriber=OpenAITranscriber(),
            synthesizer=OpenAISynthesizer(voice="alloy"),
            brain=HermesCliBrain(),
        )
    except (RuntimeError, ImportError) as exc:
        raise SystemExit(f"voice-bot configuration error: {exc}") from None
    bridge.run()
