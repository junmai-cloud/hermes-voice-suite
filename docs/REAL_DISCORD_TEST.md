# Real Discord voice test

## Preparation

1. Create a private Discord voice channel.
2. Give the bot only View Channel, Connect, Speak, Use Voice Activity, and command permissions. Do not grant Administrator.
3. Set the channel bitrate to 32kbps or lower for the mobile-data target.
4. Copy `.env.example` to `.env` on the runtime machine only and fill secrets there.
5. Load the environment without pasting secrets into chat or logs.

## Preflight

```bash
.venv/bin/voice-bot --check
```

This must show `OK` for the required tools and credentials. It does not make a Discord connection.

## Controlled session

1. Run `voice-bot` from the runtime machine.
2. Join the private voice channel from the phone.
3. Use `/join`, then `/listen`.
4. Say a short low-sensitivity test phrase.
5. Test one interruption while the bot is speaking.
6. Run `/stats` and record only the numeric result.
7. Use `/stop_listen`, then `/leave`.

## Stop conditions

Stop the session immediately if any of these occur:

- unexpected channel members can hear or speak;
- audio continues after `/stop_listen`;
- a temporary audio file remains unexpectedly;
- a token or transcript appears in logs;
- communication exceeds 40MB/hour;
- median reply latency exceeds 5 seconds;
- the bot repeats, loops, or speaks while the user is still talking.

Do not use passwords, payment details, private keys, or sensitive medical details during this first test.
