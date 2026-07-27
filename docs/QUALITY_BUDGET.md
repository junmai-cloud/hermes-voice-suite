# Voice quality and mobile-data budget

This project treats mobile data, latency, safety, and intelligibility as release gates—not afterthoughts.

## Hard budgets

| Metric | Target | Release rule |
|---|---:|---|
| Discord voice bitrate | 32 kbps maximum | Never use 64 kbps in mobile mode |
| Discord traffic estimate | ~28.8 MB/hour bidirectional payload | Alert if measured average exceeds 40 MB/hour |
| Spoken user turn | 20 seconds maximum | Ask for a shorter turn or defer details |
| Spoken assistant reply | 45 seconds maximum while driving | Summarize and defer long details |
| STT upload | WebM/Opus, not WAV/PCM | Reject uncompressed upload in mobile mode |
| Audio retention | Temporary only | Delete after delivery / timeout |
| Visual interaction | None while driving | No buttons required for ordinary turns |

## Operating modes

### Mobile driving mode

- Private Discord voice channel at 32 kbps.
- `/listen` enables VAD turn detection.
- Silence closes a turn; speech interrupts playback.
- No video, screen share, or raw audio attachments.
- Actions require explicit spoken confirmation: “実行して”.

### High-quality stationary mode

A separate channel may use higher quality when the user is parked. It must never silently change the mobile channel's budget.

## Measurement

The live bot should record counters only, not raw speech:

- voice session duration
- bytes sent and received
- number and duration of turns
- STT encoded bytes
- time to first spoken response
- interruption count
- reconnect count

No transcript or audio is retained by the metrics layer. A release is not considered production-ready until a real mobile session confirms the budget and latency targets.
