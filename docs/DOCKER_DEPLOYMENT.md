# Docker deployment

This repository now includes a staged Docker layout for the VPS:

```text
hermes-gateway   Discord voice and Hermes orchestration
codex-worker     VPS implementation worker
codex-auditor     read-only independent audit worker
codex-chat-worker  JUNMAI/Codex prompt-only read-only worker
codex-discord-bot  JUNMAI/Codex separate Discord application
```

The compose file is a deployment scaffold. It does not change the currently
running systemd service until the cutover commands are deliberately run.

The JUNMAI/Codex path is not a Hermes Gateway cutover. It is a separate Bot
and Chat Worker pair. It must not reuse the Hermes Discord token, technical
worker token, or Hermes outbound-audit path. The two services can be built and
started individually without restarting Hermes Gateway, `codex-worker`, or
`codex-auditor`.

## Why the voice service uses host networking

The Discord voice connection negotiates a UDP media session. The initial Linux
configuration uses host networking for `hermes-gateway` so the first real
voice test does not add an unverified NAT boundary. This also means the
gateway container is less isolated at the network layer. The Codex workers
remain bound to `127.0.0.1` on the VPS.

If bridge networking passes the real Discord voice test later, remove
`network_mode: host` and switch the worker URLs to the Compose service names.

## First-time setup on the VPS

Run these commands from the Git checkout. Do not use the installed
`/usr/local/lib/hermes-agent` directory as the Codex worktree.

```bash
cp .env.example .env
chmod 600 .env
```

Set the Discord/OpenAI values and create private technical and Chat Worker
tokens in `.env`. `CODEX_DISCORD_BOT_TOKEN` must belong to the separate JUNMAI
Discord application and must differ from `DISCORD_BOT_TOKEN`.
Never paste the file contents into chat or commit the file.

For the isolated JUNMAI/Codex path, the minimum required values are
`CODEX_DISCORD_BOT_TOKEN`, `CODEX_CHAT_WORKER_TOKEN`, the three configured
Discord IDs, and `OPENAI_API_KEY`. The Bot service deliberately does not use
`env_file: .env`; Compose passes only the explicitly listed values.

Build only the isolated path:

```bash
docker compose build codex-chat-worker codex-discord-bot
```

Start only the isolated path, in two targeted operations:

```bash
docker compose up -d --no-deps codex-chat-worker
docker compose up -d --no-deps codex-discord-bot
docker compose ps codex-chat-worker codex-discord-bot
docker compose logs --tail 100 codex-chat-worker codex-discord-bot
```

Confirm the Chat Worker health endpoint using the token without printing it.
Then confirm Discord login/Ready, voice-channel connection, audio receive, and
TTS playback. Do not report recovery from container state alone.

If the technical worker/auditor stack itself is being updated, build only
those images:

```bash
docker compose build codex-worker codex-auditor
```

Authenticate Codex in the persistent `codex-home` volume. On a headless VPS,
device authentication is the expected interactive path:

```bash
docker compose run --rm --entrypoint codex codex-worker login --device-auth
```

Start only the workers first:

```bash
docker compose up -d codex-worker codex-auditor
```

Check their private health endpoints:

```bash
docker compose ps
```

The auditor has a read-only repository mount and uses the Codex read-only
sandbox. The implementation worker uses a separate workspace-write sandbox.

## Cutover of Hermes

Do not run the systemd gateway and Docker gateway with the same Discord bot
token at the same time.

After worker health and a Discord test in the staged environment:

```bash
sudo systemctl stop hermes-gateway
docker compose up -d hermes-gateway
docker compose logs -f --tail=100 hermes-gateway
```

Rollback without rebooting the VPS:

```bash
docker compose stop hermes-gateway
sudo systemctl start hermes-gateway
```

The Docker gateway depends on the external `hermes` command used by
`HermesCliBrain`. That command must be packaged into the image or provided by
the final VPS image before production cutover; it is not part of this Git
repository.
