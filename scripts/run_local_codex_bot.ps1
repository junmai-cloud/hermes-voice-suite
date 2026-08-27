$ErrorActionPreference = 'Stop'
$Root = 'C:\AI\APP\hermes-voice-suite'
Set-Location $Root

# The Python entry point loads only the dedicated Codex keys from .env.
# It never starts Hermes, technical-worker, or auditor processes.
python -m voice_suite.codex_local_cli @args
