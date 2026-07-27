"""Production-style entry point for the Discord voice bot."""

import sys

from .adapters import HermesCliBrain, OpenAISynthesizer, OpenAITranscriber
from .discord_bridge import VoiceBridge, VoiceBotSettings
from .preflight import check_environment, format_report


def main() -> None:
    if "--check" in sys.argv[1:]:
        results = check_environment()
        print(format_report(results))
        if not all(result.ok for result in results):
            raise SystemExit(2)
        return
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
