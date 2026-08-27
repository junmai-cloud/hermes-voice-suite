# Local Hermes/Codex team

## Start after Windows login

From PowerShell:

```powershell
Set-Location C:\AI\APP\hermes-voice-suite
.\scripts\start_local_team.ps1
```

The two supervisors are intentionally separate:

- `local_codex_worker_supervisor.py`: waits for local `.env` token, starts Codex worker on `127.0.0.1:8767`, retries after exit.
- `local_codex_tunnel_supervisor.py`: waits for worker health and authenticated SSH, then creates a loopback-only reverse tunnel to the VPS.

Port `8765` remains reserved for the local Whisper CUDA service.

## One-time local secret provisioning

Run this locally, never in Discord:

```powershell
python .\scripts\provision_local_worker_secret.py
```

The token is entered without display and written to `.env`, which is Git-ignored. Do not paste the token into chat or commit `.env`.

## Status

```powershell
python .\scripts\local_team_status.py
```

`token=set` is only a presence check; no secret value is printed.
