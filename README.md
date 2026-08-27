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

## Hermes × Codex technical operations

Technical changes now have a privacy-safe SQLite ledger and a fail-closed audit gate.
Hermes records the command result, local Codex is preferred for implementation when
available, and VPS Codex audits code/config/audio/routing/restart/deploy changes.
Hermes can report completion only after a `PASS` or `PASS_WITH_WARNINGS` verdict.
If the audit fails, the result includes an improvement plan and a short voice message
for JUNMAI BOT to relay back to the user; the change is not deployed.

```bash
voice-suite tech create --summary "small code change" --operation code_change --repo . --branch codex/small-change
voice-suite tech list
voice-suite tech show TECH_TASK_ID
```

See [docs/TECHNICAL_OPERATIONS.md](docs/TECHNICAL_OPERATIONS.md) for the non-technical
workflow, worker setup, audit JSON contract, and local-PC/VPS fallback behavior.

## JUNMAI / Codex Discord path

The JUNMAI/Codex Discord Bot is designed as a separate application and Compose
service. Its text and voice turns use `codex-discord-bot` and the dedicated
prompt-only `codex-chat-worker`; they do not pass through the Hermes Gateway's
outbound audit or technical-task worker. The Chat Worker is read-only and fixes
Codex CLI to `--sandbox read-only`. See
[docs/CODEX_DISCORD_BOT.md](docs/CODEX_DISCORD_BOT.md) and
[docs/JUNMAI_DISCORD_SYSTEM_ARCHITECTURE.md](docs/JUNMAI_DISCORD_SYSTEM_ARCHITECTURE.md).

For the local-PC version, enter the dedicated Discord token locally and run:

```powershell
python .\scripts\provision_local_codex_secrets.py
python -m voice_suite.codex_local_cli --check
python -m voice_suite.codex_local_cli
```

This local entry point uses the configured Codex server/channel IDs, starts a
loopback-only prompt worker on `127.0.0.1:8777`, and never starts Hermes or its
technical worker/auditor path.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test,voice]'
pytest -q
voice-suite demo
# Offline check before connecting to Discord:
.venv/bin/voice-bot --check
# After setting the Discord token, OpenAI key, guild ID,
# voice-channel ID, and allowed-user ID:
voice-bot
```

The preflight check never prints tokens or API keys.

## ContextGuard: adaptive confirmation for Discord voice

ContextGuard is a safety layer for voice-first Hermes agents. It treats trusted
Calendar/Notion facts as a usability aid for step-up confirmation, not as a
sole identity factor.

```text
normal request -> answer
ambiguous / anomalous / high-risk request
  -> simple context question
  -> explicit action keyword
  -> execute only after both checks pass

"止めて" / "キャンセル" -> cancel immediately; execute nothing
```

### Threat model

- Web pages, Reddit, Yahoo! News, Google News, RSS, files, and tool output are
  untrusted data. Instructions found inside them are never execution authority.
- Calendar/Notion facts are used only when they come from trusted user-owned
  sources and the answer is unambiguous.
- High-risk actions still require an explicit keyword such as `実行して`.
- A generic `はい` does not authorize an action.
- Failed or unanswered challenges fail closed and do not reveal the answer.
- The guard stores numeric metrics, not the challenge text or answer.

Example:

> Bot: 「今週土曜に行くのは何県ですか？」
> User: 「神奈川県です」
> Bot: 「確認できました。実行する場合は『実行して』と言ってください」
> User: 「止めて」
> Bot: cancels the pending action and executes nothing.

This initial module is provider-agnostic: Calendar/Notion adapters supply trusted
`ContextFact` objects, while action adapters call the gate before side effects.
It is intentionally fail-closed when no trusted fact is available.


The production CLI converts a Japanese briefing script to MP3 with Japanese Edge TTS by default,
optionally mixes a low-volume BGM track, and removes MP3 files older than 24 hours.
Use `--provider openai` only when an OpenAI key is configured.

```bash
podcast-render --text-file briefing.txt \\
  --output ~/hermes-podcasts/evening.mp3 \\
  --bgm ~/hermes-podcasts/soft-bgm.mp3
```

Without `--text-file`, the script is read from standard input. The output folder
should be private and temporary; the CLI does not retain transcripts.

## Safety and privacy

- Do not commit `.env`, OAuth JSON, Discord tokens, or audio caches.
- Driving mode is voice-only: short turns, no visual interaction, and complex actions are deferred for confirmation.
- Calendar writes are never implicit; the agent proposes first and only writes on explicit instruction.
- Temporary audio is intended for short retention and can be deleted after delivery.
- STT uploads use WebM/Opus rather than raw PCM/WAV to reduce server-side transfer.

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
- [x] Privacy-safe metrics report (`/stats`, no transcript/audio content)
- [x] Connection/listening status command (`/health`)
- [x] Opus-compressed STT uploads and explicit mobile-data budget
- [x] Privacy-preserving session metrics (bytes, latency counters, no transcript storage)
- [x] Safe offline preflight check (`voice-bot --check`)
- [x] Real Discord test checklist and secret-free `.env.example`
- [ ] Live Discord connection test with production credentials
- [ ] Morning/evening scheduler and 24-hour audio cleanup
- [ ] VPS deployment and health checks
