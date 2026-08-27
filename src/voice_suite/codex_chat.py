"""Standalone read-only chat worker for the JUNMAI/Codex Discord bot.

This module intentionally has no dependency on the Hermes technical-operation
stack.  It exposes a small prompt-only HTTP API and always starts Codex CLI
with the immutable ``--sandbox read-only`` policy.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


class ChatRequestError(ValueError):
    """Raised when a chat request is not prompt-only and valid."""


class ChatWorkerUnavailable(RuntimeError):
    """Raised when the Codex CLI cannot be used for a chat request."""


class ChatWorkerTimeout(TimeoutError):
    """Raised when Codex does not answer within the configured deadline."""


@dataclass(frozen=True)
class ChatWorkerConfig:
    """Configuration that does not expose any task or mutation controls."""

    command: str = "codex"
    working_directory: str | Path | None = None
    timeout_seconds: float = 90.0
    max_prompt_chars: int = 6000
    max_response_chars: int = 12000

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_prompt_chars < 1 or self.max_response_chars < 1:
            raise ValueError("chat character limits must be positive")


_CHILD_ENV_KEYS = (
    "PATH",
    "HOME",
    "CODEX_HOME",
    "OPENAI_API_KEY",
    "LANG",
    "LC_ALL",
    "TERM",
    "NO_COLOR",
    "TMPDIR",
    "TMP",
    "TEMP",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
)
_SECRET_ENV_MARKERS = ("TOKEN", "KEY", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH")


def _child_environment() -> dict[str, str]:
    """Pass only the environment needed by Codex, never the whole parent env."""

    return {key: os.environ[key] for key in _CHILD_ENV_KEYS if os.environ.get(key) is not None}


def _redact_secrets(value: str) -> str:
    """Remove known secret-like environment values from a worker response."""

    redacted = value
    for key, secret in os.environ.items():
        if not secret or len(secret) < 8 or not any(marker in key.upper() for marker in _SECRET_ENV_MARKERS):
            continue
        redacted = redacted.replace(secret, "[redacted]")
    return redacted


def _command_prefix(executable: str) -> list[str]:
    """Return an executable prefix, including PowerShell shims."""

    suffix = Path(executable).suffix.lower()
    if suffix == ".ps1":
        powershell = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
        return [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", executable]
    return [executable]


def _truncate(value: str, limit: int) -> str:
    value = value or ""
    if len(value) <= limit:
        return value
    return value[:limit] + "\n[truncated]"


def _clean_prompt(prompt: Any, *, max_chars: int) -> str:
    if not isinstance(prompt, str):
        raise ChatRequestError("prompt must be a string")
    cleaned = " ".join(prompt.split()).strip()
    if not cleaned:
        raise ChatRequestError("prompt must not be empty")
    if len(cleaned) > max_chars:
        raise ChatRequestError(f"prompt exceeds the {max_chars}-character limit")
    return cleaned


class CodexReadOnlyChatWorker:
    """Run one prompt at a time through Codex CLI in read-only mode.

    The public method accepts only a prompt.  There is no task, repository,
    branch, audit, ledger, or sandbox parameter in this worker contract.
    """

    def __init__(self, config: ChatWorkerConfig | None = None) -> None:
        self.config = config or ChatWorkerConfig()
        self._lock = threading.Lock()

    def executable(self) -> str | None:
        return shutil.which(self.config.command)

    def status(self) -> dict[str, Any]:
        executable = self.executable()
        return {
            "state": "ready" if executable else "unavailable",
            "capabilities": ["prompt-only", "read-only"],
            "message": "" if executable else f"{self.config.command} not found",
        }

    def build_command(self, prompt: str) -> list[str]:
        """Build the only permitted Codex invocation for a prompt."""

        cleaned = _clean_prompt(prompt, max_chars=self.config.max_prompt_chars)
        executable = self.executable()
        if executable is None:
            raise ChatWorkerUnavailable(f"Codex executable not found: {self.config.command}")
        # Keep this literal and local: a caller cannot select another sandbox.
        return _command_prefix(executable) + [
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--",
            cleaned,
        ]

    def _working_directory(self) -> str | None:
        if self.config.working_directory is None:
            return None
        path = Path(self.config.working_directory).expanduser()
        if not path.is_absolute():
            raise ChatWorkerUnavailable("chat working directory must be absolute")
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise ChatWorkerUnavailable("chat working directory is unavailable") from exc
        if path != resolved or not resolved.is_dir() or resolved == Path(resolved.anchor):
            raise ChatWorkerUnavailable("chat working directory must be a non-root real directory")
        return str(resolved)

    def answer(self, prompt: str) -> str:
        """Return Codex's answer to one prompt without accepting task metadata."""

        command = self.build_command(prompt)
        cwd = self._working_directory()
        child_env = _child_environment()
        with self._lock:
            returncode, stdout = self._run_command(command, cwd=cwd, env=child_env)

        if returncode != 0:
            raise ChatWorkerUnavailable("Codex chat failed")
        response = _redact_secrets(
            _truncate(stdout.decode("utf-8", errors="replace").strip(), self.config.max_response_chars)
        )
        if not response:
            raise ChatWorkerUnavailable("Codex returned an empty response")
        return response

    def _run_command(self, command: list[str], *, cwd: str | None, env: dict[str, str]) -> tuple[int, bytes]:
        """Run Codex while bounding captured output and enforcing a deadline."""
        stdout_limit = max(4_096, self.config.max_response_chars * 4)
        stderr_limit = 64 * 1024
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise ChatWorkerUnavailable("Codex executable could not be started") from exc

        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        overflow = threading.Event()

        def drain(stream, chunks: list[bytes], limit: int) -> None:
            total = 0
            try:
                while True:
                    chunk = stream.read(8192)
                    if not chunk:
                        return
                    remaining = limit - total
                    if remaining > 0:
                        chunks.append(chunk[:remaining])
                    total += len(chunk)
                    if total > limit:
                        overflow.set()
                        return
            finally:
                stream.close()

        readers = [
            threading.Thread(target=drain, args=(process.stdout, stdout_chunks, stdout_limit), daemon=True),
            threading.Thread(target=drain, args=(process.stderr, stderr_chunks, stderr_limit), daemon=True),
        ]
        for reader in readers:
            reader.start()

        deadline = time.monotonic() + self.config.timeout_seconds
        timed_out = False
        while process.poll() is None:
            if overflow.is_set():
                self._terminate_process(process)
                break
            if time.monotonic() >= deadline:
                timed_out = True
                self._terminate_process(process)
                break
            time.sleep(0.02)

        if overflow.is_set():
            self._terminate_process(process)
        if timed_out:
            self._terminate_process(process)
        process.wait()
        for reader in readers:
            reader.join(timeout=1)
        if overflow.is_set():
            raise ChatWorkerUnavailable("Codex output exceeded the configured limit")
        if timed_out:
            raise ChatWorkerTimeout("Codex chat timed out")
        return process.returncode, b"".join(stdout_chunks)

    @staticmethod
    def _terminate_process(process) -> None:
        try:
            process.kill()
        except (OSError, ProcessLookupError):
            return


class ChatWorkerHTTPServer:
    """Authenticated prompt-only HTTP API for ``CodexReadOnlyChatWorker``."""

    def __init__(
        self,
        worker: CodexReadOnlyChatWorker,
        host: str,
        port: int,
        token: str,
        *,
        max_body_bytes: int = 16_384,
        max_concurrent_requests: int = 8,
    ) -> None:
        if not token.strip():
            raise ValueError("chat worker token must not be empty")
        if max_body_bytes < 1:
            raise ValueError("max_body_bytes must be positive")
        if max_concurrent_requests < 1:
            raise ValueError("max_concurrent_requests must be positive")
        self.worker = worker
        self.token = token
        self.max_body_bytes = max_body_bytes
        self.server = _BoundedThreadingHTTPServer(
            (host, port),
            self._handler(),
            max_concurrent_requests=max_concurrent_requests,
        )

    def serve_forever(self) -> None:
        self.server.serve_forever()

    def shutdown(self) -> None:
        self.server.shutdown()

    def server_close(self) -> None:
        """Close the listening socket after ``shutdown`` has returned."""

        self.server.server_close()

    def _handler(self):
        worker = self.worker
        expected_token = self.token
        max_body_bytes = self.max_body_bytes

        class Handler(BaseHTTPRequestHandler):
            server_version = "CodexChat/1.0"

            def setup(self) -> None:
                super().setup()
                self.connection.settimeout(15)

            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def _authorized(self) -> bool:
                return self.headers.get("Authorization", "") == f"Bearer {expected_token}"

            def _send(self, status: int, payload: dict[str, Any]) -> None:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _read_json(self) -> dict[str, Any]:
                raw_length = self.headers.get("Content-Length")
                if raw_length is None:
                    raise ChatRequestError("Content-Length is required")
                try:
                    length = int(raw_length)
                except ValueError as exc:
                    raise ChatRequestError("invalid Content-Length") from exc
                if length < 0 or length > max_body_bytes:
                    raise ChatRequestError("request body is too large")
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError, TimeoutError) as exc:
                    raise ChatRequestError("request body must be valid JSON") from exc
                if not isinstance(payload, dict):
                    raise ChatRequestError("request body must be a JSON object")
                return payload

            def do_GET(self) -> None:  # noqa: N802
                if not self._authorized():
                    self._send(401, {"error": "unauthorized"})
                    return
                if self.path != "/health":
                    self._send(404, {"error": "not found"})
                    return
                self._send(200, worker.status())

            def do_POST(self) -> None:  # noqa: N802
                if not self._authorized():
                    self._send(401, {"error": "unauthorized"})
                    return
                if self.path != "/chat":
                    self._send(404, {"error": "not found"})
                    return
                try:
                    payload = self._read_json()
                    if set(payload) != {"prompt"}:
                        raise ChatRequestError("only the prompt field is accepted")
                    response = worker.answer(payload["prompt"])
                except ChatRequestError as exc:
                    self._send(400, {"error": str(exc)})
                    return
                except ChatWorkerTimeout as exc:
                    self._send(504, {"error": str(exc)})
                    return
                except ChatWorkerUnavailable as exc:
                    self._send(503, {"error": str(exc)})
                    return
                self._send(200, {"response": response})

            def do_PUT(self) -> None:  # noqa: N802
                self._send(405, {"error": "method not allowed"})

            def do_DELETE(self) -> None:  # noqa: N802
                self._send(405, {"error": "method not allowed"})

        return Handler


class _BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Keep unauthenticated or slow clients from creating unlimited threads."""

    daemon_threads = True

    def __init__(self, server_address, handler_class, *, max_concurrent_requests: int):
        self._request_slots = threading.BoundedSemaphore(max_concurrent_requests)
        super().__init__(server_address, handler_class)

    def process_request(self, request, client_address):
        if not self._request_slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


def worker_from_environment() -> CodexReadOnlyChatWorker:
    """Build a worker from chat-only environment variables."""

    try:
        timeout = float(os.environ.get("CODEX_CHAT_TIMEOUT", "90"))
    except ValueError as exc:
        raise ValueError("CODEX_CHAT_TIMEOUT must be a number") from exc
    try:
        max_prompt_chars = int(os.environ.get("CODEX_CHAT_MAX_PROMPT_CHARS", "6000"))
        max_response_chars = int(os.environ.get("CODEX_CHAT_MAX_RESPONSE_CHARS", "12000"))
    except ValueError as exc:
        raise ValueError("chat character limits must be integers") from exc
    working_directory = os.environ.get("CODEX_CHAT_WORKDIR") or os.environ.get("CODEX_REPO_PATH")
    if not working_directory:
        raise ValueError("CODEX_CHAT_WORKDIR or CODEX_REPO_PATH is required")
    return CodexReadOnlyChatWorker(
        ChatWorkerConfig(
            command=os.environ.get("CODEX_CHAT_COMMAND", "codex").strip() or "codex",
            working_directory=working_directory,
            timeout_seconds=timeout,
            max_prompt_chars=max_prompt_chars,
            max_response_chars=max_response_chars,
        )
    )
