# Codex Discord Bot

The Codex bot is a separate Discord application and a separate Compose
service. It does not reuse the Hermes Discord token, technical-worker token,
or Hermes gateway process.

## Isolation contract

The Compose graph is intentionally split into two paths:

```text
Hermes Gateway -> codex-worker / codex-auditor

codex-discord-bot -> codex-chat-worker
```

- `codex-discord-bot` has no `env_file`; it receives only the explicitly
  listed Discord, OpenAI, model, and Chat Worker settings.
- `CODEX_DISCORD_BOT_TOKEN` is used only by the Bot and must differ from
  Hermes' `DISCORD_BOT_TOKEN`.
- `CODEX_CHAT_WORKER_TOKEN` is used only between the Bot and the dedicated
  `codex-chat-worker`; it must differ from the technical `CODEX_WORKER_TOKEN`.
- `CODEX_CHAT_WORKER_URL` points to the prompt-only `/chat` endpoint; it is not
  the technical worker `/jobs` endpoint.
- `codex-chat-worker` uses `/codex-chat-home`, a dedicated named volume, a
  read-only `/workspace` mount, `read_only: true`, `/tmp` tmpfs, and the
  source-fixed `--sandbox read-only` Codex command argument. It receives the
  existing OpenAI credential explicitly because its dedicated Codex home is
  intentionally not shared with the technical worker.
- The Chat Worker has no dependency on the Hermes Gateway, technical Worker,
  or Auditor. The Bot depends only on the Chat Worker.

The existing `hermes-gateway`, `codex-worker`, and `codex-auditor` service
definitions remain separate and are not replaced by this path.

## Local PC launch

For the local-PC version, the repository provides one entry point that starts
the prompt-only Chat Worker on loopback and then starts the separate Discord
Bot in the same process:

```powershell
Set-Location C:\AI\APP\hermes-voice-suite
python -m voice_suite.codex_local_cli --check
python -m voice_suite.codex_local_cli
# or: .\scripts\run_local_codex_bot.ps1
```

If the dedicated Bot token has not been entered into the local ignored
`.env`, provision it interactively (the value is hidden and a separate local
Chat Worker token is generated automatically):

```powershell
python .\scripts\provision_local_codex_secrets.py
```

The local entry point reads only the dedicated `CODEX_*` Discord/Chat Worker
settings and `OPENAI_API_KEY` from `.env`. It does not load
`DISCORD_BOT_TOKEN`, `CODEX_WORKER_TOKEN`, or start the Hermes Gateway,
technical worker, or auditor. The Chat Worker is bound to `127.0.0.1:8777`
and invokes Codex with a source-fixed `--sandbox read-only` flag.

## Discord resources

- Server: `コデックスの純米サーバー`
- Application/Bot: `コデックスの純米ボット`
- Guild ID: `1539771881731788990`
- Text channel `一般`: `1539771882642079817`
- Voice channel `一般`: `1539771882642079818`

The first runtime is restricted to the server and the two configured channels.
`CODEX_DISCORD_ALLOWED_USER_ID` can be added to restrict it to one Discord
user as well.

## Runtime behavior

- Plain text messages in the configured text channel are answered.
- `/ask` sends a read-only question to the Codex chat worker.
- `/join`, `/record`, `/stop`, `/listen`, `/stop_listen`, `/leave`, `/health`,
  and `/stats` use the shared voice bridge with OpenAI STT/TTS adapters.
- The chat worker uses `read-only` Codex sandboxing and a read-only repository
  mount. Discord chat does not directly apply code changes.

## Secrets

Set these only in the VPS `.env` file. Never commit or paste the values into
chat:

```dotenv
# Existing Hermes path
DISCORD_BOT_TOKEN=...
CODEX_WORKER_TOKEN=...

# Isolated Codex Discord path
CODEX_DISCORD_BOT_TOKEN=...
CODEX_CHAT_WORKER_TOKEN=...
CODEX_CHAT_WORKER_URL=http://127.0.0.1:8777
CODEX_DISCORD_GUILD_ID=1539771881731788990
CODEX_DISCORD_TEXT_CHANNEL_ID=1539771882642079817
CODEX_DISCORD_VOICE_CHANNEL_ID=1539771882642079818
OPENAI_API_KEY=...
```

The Bot token and Chat Worker token must be different from the corresponding
Hermes and technical-worker credentials. Do not add `env_file: .env` to the
Bot service: explicit Compose environment entries are the credential
boundary.
