# AGENTS.md — Hermes Voice Suite

These instructions apply to the whole repository. They describe the current
voice pipeline, the Hermes/Codex operating model, and the safe way to reach the
Hub VPS from this Windows development machine.

## Project map

- `src/voice_suite/discord_bridge.py`: Discord voice commands, two-stage STT,
  playback interruption, and voice authorization.
- `src/voice_suite/streaming.py`: PCM collection and silence-based turn
  boundaries.
- `src/voice_suite/technical_ops.py`: task, audit, worker, and state contracts.
- `src/voice_suite/technical_service.py`: local/VPS worker routing and audit
  orchestration.
- `src/voice_suite/technical_ledger.py`: privacy-safe SQLite task ledger.
- `tests/`: dependency-light unit and integration tests.
- `compose.yaml`: staged VPS stack for Hermes Gateway, VPS Codex worker, and
  read-only VPS Codex auditor.
- `docs/HERMES_COMPANY_OPERATIONS.md`: Hermes/Codex company boundary, local burst routing, and audit contract.
- `docs/DOCKER_DEPLOYMENT.md`: staged Docker deployment and cutover notes.

The project targets Python 3.11. Keep Discord, STT, TTS, and network code at
adapter boundaries so the core remains testable without production secrets.

## Local development

Run the full test suite after code changes:

```bash
pytest -q
```

Use the voice preflight without connecting to Discord when possible:

```bash
.venv/bin/voice-bot --check
```

Do not commit `.env`, OAuth files, Discord tokens, API keys, audio, transcripts,
runtime databases, or private SSH material. `.env`, `codex-ssh-config`, and
runtime/cache paths are intentionally ignored by Git.

Use a `codex/...` branch or worktree for code changes. Do not edit an installed
Hermes runtime or a production checkout as the implementation worktree.

## Hermes/Codex technical-operation policy

Hermes is the requester, executor, and voice reporter. It is not the final
technical approver. A technical change follows this path:

```text
REQUESTED -> PLANNED -> IMPLEMENTING -> VERIFYING -> APPROVED -> DEPLOYED
```

Use `NEEDS_FIX`, `BLOCKED`, or `CANCELLED` when appropriate.

### Audit levels

Read-only inspection, log viewing, process checks, and existing tests may be
performed without an independent audit. The following always require the VPS
Codex auditor before completion or deployment:

- code, configuration, dependency, audio-pipeline, or routing changes;
- service restarts, deployment, authentication, permission, or network changes;
- changes to Hermes/Gateway integration or the local-PC/VPS worker route;
- destructive or production-data operations.

Every command result should record the command, expected result, actual result,
exit code, changed files, tests, health checks, and next action. Do not store
voice transcripts, raw audio, tokens, or secrets in the technical ledger.

An audit result must be strict JSON with `PASS`, `PASS_WITH_WARNINGS`, `FAIL`, or
`BLOCKED`, plus rationale, evidence, issues, improvement plan, production
readiness, and rollback plan. Missing, truncated, or vague evidence is not a
pass. Hermes/JUNMAI may say a technical change is complete only after
`PASS`/`PASS_WITH_WARNINGS`; on `FAIL` or `BLOCKED`, relay the auditor's
improvement plan and do not deploy.

Prefer a ready local Codex worker for implementation. Use the VPS worker as the
fallback when the local PC is unavailable. The VPS auditor remains independent.
One task ID must have one implementation owner; never let local and VPS workers
edit the same task at the same time.

## Voice-streaming invariants

The current voice design intentionally uses a two-stage turn:

- the first 2,000 ms is submitted as one early STT task;
- the remainder is submitted as one tail task after the turn boundary;
- a 400 ms overlap protects words at the boundary;
- results are merged once, without an unbounded chunk queue;
- only one early task per user may be active;
- early tasks are cancelled and awaited on voice leave/disconnect.

Do not revert this to a full-utterance-only path or create an unbounded queue
without a new `audio_pipeline_change` task, tests, audit evidence, and a
rollback plan. Preserve voice authorization, playback interruption, and
privacy-safe metrics while changing latency behavior.

### Local GPU Whisper sidecar on Windows

The local Hermes STT configuration uses `provider: whisper-service`. That
provider calls `C:\AI\TEMP\whisper-service\client.py`, which sends audio to
the loopback service at `http://127.0.0.1:8765/transcribe`. The service loads
Whisper medium with `device="cuda"` and is therefore the GPU-backed local
voice-recognition path, not an optional console utility.

The login startup entry
`C:\Users\aspop\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\HermesWhisperGPU.bat`
must remain enabled whenever that STT provider is active. It should launch
the service through `pythonw.exe` so the service runs in the background without
opening a PowerShell/console window. Do not delete the launcher or change the
service to CPU unless the STT provider, performance impact, tests, audit
evidence, and rollback plan are updated together.

## Hub VPS access from Codex

The Hub VPS is reached from this Windows host through the repository-local,
non-secret SSH config:

```bash
ssh -F C:/AI/APP/hermes-voice-suite/codex-ssh-config hub-vps
```

The alias resolves to `deployuse@133.88.122.185` and uses the private key at
`C:/Users/aspop/.ssh/hermes_conoha`. Never print, copy, commit, or expose the
private key. Do not use `root@133.88.122.185`; root key authentication is not
enabled. The `deployuse` account has Docker access but does not have
passwordless `sudo`.

Before any remote mutation, verify the target:

```bash
ssh -F C:/AI/APP/hermes-voice-suite/codex-ssh-config hub-vps \
  'whoami; hostname; pwd'
```

The remote Compose project is currently `/root/hermes-voice-suite-docker`.
Docker labels identify that path even when the `deployuser` shell cannot read
the root-owned checkout directly. Do not change ownership or permissions just
to make inspection easier; use Docker's read-only inspection commands or obtain
explicit approval for a narrowly scoped privilege change.

Useful read-only checks include:

```bash
docker ps
docker logs --tail 100 hermes-voice-suite-hermes-gateway-1
docker compose ps
```

Worker and auditor ports are private to the VPS:

- worker: `127.0.0.1:8765`
- auditor: `127.0.0.1:8766`

Use the bearer token from the remote `.env` only in the remote shell. Never
print the token or paste `.env` contents into chat or logs.

## Docker and Gateway cutover safety

The Compose services are:

```text
hermes-gateway  Discord voice and Hermes orchestration
codex-worker    VPS implementation worker, workspace-write
codex-auditor  independent read-only audit worker
```

Start and validate workers before considering Gateway cutover. The Gateway uses
host networking for the first real Discord UDP voice test and mounts the
installed Hermes runtime and `/root/.hermes` read-only. It requires
`DISCORD_BOT_TOKEN`; if that variable is absent, the container will restart in
a loop and must not be treated as healthy.

Never run the systemd/host Hermes Gateway and the Docker Gateway with the same
Discord bot token at the same time. A cutover is a `restart`/`deploy` operation:
it requires a technical task, tests, VPS audit, explicit user approval, and a
rollback plan. Do not reboot the VPS for a Gateway change. Prefer a targeted
service/container action and verify Discord health after it.

The staged rollback is:

```bash
docker compose stop hermes-gateway
sudo systemctl start hermes-gateway
```

Do not execute cutover or rollback automatically merely because a Docker health
check fails. First capture logs and status, identify which Gateway currently
owns the Discord token, and report the impact.

## Local Codex JUNMAI Bot installation

When the VPS is inaccessible or temporarily banned, do not block the local bot
installation on VPS access. Read `docs/CODEX_LOCAL_VPS_INSTALLATION_TIPS.md`.
The local entry point is `python -m voice_suite.codex_local_cli`; its dedicated
Discord token and prompt-only Chat Worker are local-only. Verify `--check`, the
loopback worker health, Discord guild/channel restrictions, and one real prompt
before calling the bot established. Do not start the same Discord token on VPS
and local at the same time.

## Completion checklist

Before reporting work as complete:

1. inspect the diff and confirm no secrets or generated runtime files are present;
2. run the relevant tests, normally `pytest -q`;
3. perform targeted health checks without exposing credentials;
4. submit the required VPS Codex audit with evidence and rollback information;
5. report `PASS`/`PASS_WITH_WARNINGS`, warnings, remaining risks, and the next
   action in a short voice-friendly summary.

If any required evidence is missing, report the task as incomplete or blocked.
