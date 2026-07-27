# Security and privacy model

## Trust boundaries

```text
スマホ ⇄ Discord音声基盤 ⇄ Voice Bot/VPS ⇄ STT provider
                                      ⇄ Hermes/model provider
```

- Discord transport encryption protects traffic in transit, but the Voice Bot is an endpoint: it must receive usable audio to transcribe and reply.
- The bot operator, VPS, STT provider, and model provider are therefore trusted components for the current design.
- This is not a promise that the bot conversation is private from every provider. A future provider with local STT/TTS is required for a stronger privacy posture.

## Data handling

### Audio

- VAD processes PCM in memory where possible.
- STT uploads are WebM/Opus, not raw PCM/WAV.
- Temporary files use OS temporary storage and are deleted after processing/playback.
- No continuous recording archive is enabled by default.
- Voice channel sessions must be started explicitly with `/listen`.

### Transcripts and model prompts

- The application does not write transcripts to its own database or metrics.
- Hermes/model providers may process the text according to their account and API retention settings; configure provider data controls separately.
- Do not discuss passwords, payment card numbers, private keys, or highly sensitive medical details while connected to the voice bot.

### Metrics

Only counters are retained by the metrics layer: byte counts, durations, turn counts, response time, and interruptions. Audio and transcript content are excluded by design.

## Credential rules

- Store `DISCORD_BOT_TOKEN` and `OPENAI_API_KEY` only in the runtime environment or a protected secret manager.
- Never commit OAuth JSON, `.env`, tokens, or audio caches.
- Use a bot with only the permissions required for the private voice channel: View Channel, Connect, Speak, Use Voice Activity, and minimal command/message permissions.
- Do not grant Administrator.
- Rotate any credential that appears in chat, logs, screenshots, or a public repository.

## Operational release gates

Before enabling a real mobile session:

1. Confirm the bot account and all providers are approved for this data.
2. Use a private channel with a known member list.
3. Verify no audio or transcript remains after a test session.
4. Verify byte and latency budgets over at least a 30-minute session.
5. Test bot disconnect/reconnect and temporary provider failure.
6. Display a clear voice-session indicator and provide `/stop_listen`.

## Known limitation

Discord-side end-to-end encryption does not make the bot blind to audio: the bot must be able to decode the stream. For highly confidential conversations, use local STT/TTS on a trusted machine and keep the audio inside that trust boundary.
