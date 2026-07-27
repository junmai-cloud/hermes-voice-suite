# Hermes Voice Suite

A voice-first personal agent built around two connected workflows:

1. **Daily podcast briefings** — calendar-aware morning/evening scripts with one proactive suggestion.
2. **Discord meeting mode** — a mobile-friendly voice meeting layer that routes speech to an agent and speaks back without echoing the user.

> Early open-source foundation. Secrets stay in environment variables; no Discord or Google credentials are committed.

## Architecture

```text
Discord mobile voice
        | STT / VAD / interrupt
        v
MeetingOrchestrator  <-->  Hermes tools and memory
        | TTS
        v
Discord voice playback

Calendar + news + user context -> BriefingComposer -> TTS -> Discord attachment
```

The core is dependency-light and testable without network credentials. Discord/STT/TTS adapters are optional boundaries so the conversation policy can be tested locally first.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
pytest -q
voice-suite demo
```

## Safety and privacy

- Do not commit `.env`, OAuth JSON, Discord tokens, or audio caches.
- Driving mode is voice-only: short turns, no visual interaction, and complex actions are deferred for confirmation.
- Calendar writes are never implicit; the agent proposes first and only writes on explicit instruction.
- Temporary audio is intended for short retention and can be deleted after delivery.

## Roadmap

- [x] Shared briefing and meeting policies
- [x] Deterministic local demo and tests
- [ ] Google Calendar adapter using the existing Hermes token
- [ ] Japanese STT/TTS adapter
- [x] Discord voice receive/playback bridge prototype (`/join`, `/record`, `/stop`, `/leave`)
- [x] Pluggable Hermes CLI brain and OpenAI STT/TTS adapters
- [x] Energy VAD and barge-in control primitives
- [x] Pycord streaming sink for automatic turn boundaries
- [x] Voice playback with speech interruption (`/listen`, `/stop_listen`)
- [ ] Live Discord connection test with production credentials
- [ ] Morning/evening scheduler and 24-hour audio cleanup
- [ ] VPS deployment and health checks
