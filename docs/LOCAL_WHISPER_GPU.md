# Local GPU Whisper service

Hermes uses a local Whisper sidecar for Japanese voice recognition.

## Runtime contract

- Hermes configuration: `stt.enabled: true` and `stt.provider: whisper-service`
- Client: `C:\AI\TEMP\whisper-service\client.py`
- Service: `C:\AI\TEMP\whisper-service\server.py`
- Endpoint: `http://127.0.0.1:8765`
- Model: Whisper `medium`
- Device: CUDA/GPU (`device="cuda"`, `compute_type="float16"`)
- Startup: `C:\Users\aspop\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\HermesWhisperGPU.bat`

The service is intentionally started at Windows logon so Hermes can use local
GPU transcription without waiting for model initialization on the first voice
request. It binds to loopback only; it is not intended to be a public network
service.

The startup launcher checks `/health` first and starts the service only when it
is not already available. It uses `pythonw.exe`, so the GPU service stays in
the background without opening a console window. The launcher should not be
deleted or disabled while `stt.provider` remains `whisper-service`.

## Verification

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

Expected response includes `ok: true`, `model: medium`, and `device: cuda`.
