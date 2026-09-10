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

## ConoHa SSH setup and ban avoidance

Copy `codex-ssh-config.example` to the ignored `codex-ssh-config` file and
confirm that `C:\Users\aspop\.ssh\hermes_conoha` exists. Never copy or print
the private key. Before starting the supervisor, perform one configuration-only
check and then one authenticated check:

```powershell
Copy-Item .\codex-ssh-config.example .\codex-ssh-config
ssh -F .\codex-ssh-config -G hub-vps | Out-Null
ssh -F .\codex-ssh-config -o BatchMode=yes hub-vps 'whoami; hostname; pwd'
```

Do not repeatedly test while the source address is banned. The tunnel
supervisor makes no network attempt when its config is absent or invalid, uses
only the configured identity, and exponentially backs off failed connections
from 60 seconds to one hour. It also opens the tunnel directly rather than
performing a second authentication probe first.
