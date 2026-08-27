$ErrorActionPreference = 'Stop'
$Root = 'C:\AI\APP\hermes-voice-suite'
$Python = (Get-Command python).Source

function Start-IfMissing([string]$ScriptName, [string]$Title) {
    $running = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.CommandLine -like "*$ScriptName*" }
    if (-not $running) {
        Start-Process -FilePath $Python -WorkingDirectory $Root -WindowStyle Minimized -ArgumentList @(
            "$Root\scripts\$ScriptName"
        )
        Write-Output "started: $Title"
    } else {
        Write-Output "already running: $Title"
    }
}

Start-IfMissing 'local_codex_worker_supervisor.py' 'worker supervisor'
Start-IfMissing 'local_codex_tunnel_supervisor.py' 'tunnel supervisor'
Start-IfMissing 'local_codex_bot_supervisor.py' 'Codex JUNMAI bot supervisor'
