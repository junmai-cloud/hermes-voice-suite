# Docker deployment

This repository now includes a staged Docker layout for the VPS:

```text
hermes-gateway   Discord voice and Hermes orchestration
codex-worker     VPS implementation worker
codex-auditor   read-only independent audit worker
```

The compose file is a deployment scaffold. It does not change the currently
running systemd service until the cutover commands are deliberately run.

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

Set the Discord/OpenAI values and create a private worker token in `.env`.
Never paste the file contents into chat or commit the file.

Build the images:

```bash
docker compose build
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
