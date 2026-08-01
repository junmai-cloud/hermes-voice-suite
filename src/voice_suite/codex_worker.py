"""Local and remote Codex worker boundaries.

The VPS and local PC use the same worker contract.  A remote worker talks over
an already protected network path (for example WireGuard) and adds a bearer
token at the application layer.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .technical_ops import (
    CodexWorker,
    TechnicalTask,
    WorkerRole,
    WorkerState,
    WorkerStatus,
    WorkerResult,
    WorkerUnavailable,
    utc_now,
)


def _truncate(value: str, limit: int = 12_000) -> str:
    value = value or ""
    return value if len(value) <= limit else value[:limit] + "\n[truncated]"


def _git_repo(path: str | Path) -> bool:
    candidate = Path(path)
    if not candidate.is_dir():
        return False
    result = subprocess.run(
        ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _git_branch(path: str | Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "branch", "--show-current"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


class CodexCliWorker:
    """Run Codex CLI jobs on the current machine."""

    def __init__(
        self,
        worker_id: str,
        *,
        role: WorkerRole,
        command: str = "codex",
        sandbox: str = "workspace-write",
        default_repo: str | Path | None = None,
    ) -> None:
        self.worker_id = worker_id
        self.role = role
        self.command = command
        self.sandbox = sandbox
        self.default_repo = Path(default_repo) if default_repo else None
        self._jobs: dict[str, subprocess.Popen[str]] = {}
        self._lock = threading.Lock()

    def status(self) -> WorkerStatus:
        executable = shutil.which(self.command)
        if executable is None:
            return WorkerStatus(
                self.worker_id, self.role, WorkerState.UNAVAILABLE, message=f"{self.command} not found"
            )
        with self._lock:
            active = any(process.poll() is None for process in self._jobs.values())
        if active:
            return WorkerStatus(self.worker_id, self.role, WorkerState.BUSY, utc_now(), ("codex",))
        if self.default_repo and not _git_repo(self.default_repo):
            return WorkerStatus(
                self.worker_id, self.role, WorkerState.UNAVAILABLE, message="default repository is not a git repo"
            )
        return WorkerStatus(self.worker_id, self.role, WorkerState.READY, utc_now(), ("codex",))

    def submit(self, task: TechnicalTask, prompt: str) -> str:
        if not prompt.strip():
            raise ValueError("Codex prompt must not be empty")
        repo = Path(task.repo_path or self.default_repo or "")
        if not _git_repo(repo):
            raise WorkerUnavailable(f"not a git repository: {repo}")
        if task.audit_required and task.branch and _git_branch(repo) != task.branch:
            raise WorkerUnavailable(
                f"repository is not checked out on task branch {task.branch!r}; refusing direct production edits"
            )
        executable = shutil.which(self.command)
        if executable is None:
            raise WorkerUnavailable(f"Codex executable not found: {self.command}")
        command = self._command_prefix(executable) + ["exec", "--sandbox", self.sandbox, prompt]
        process = subprocess.Popen(
            command,
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=(os.name != "nt"),
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        job_id = f"job-{uuid.uuid4().hex}"
        with self._lock:
            self._jobs[job_id] = process
        return job_id

    def collect_result(self, job_id: str) -> WorkerResult:
        process = self._get_job(job_id)
        code = process.poll()
        if code is None:
            return WorkerResult(job_id, self.worker_id, "running")
        stdout, stderr = process.communicate()
        with self._lock:
            self._jobs.pop(job_id, None)
        state = "completed" if code == 0 else "failed"
        return WorkerResult(job_id, self.worker_id, state, code, _truncate(stdout), _truncate(stderr))

    def cancel(self, job_id: str) -> None:
        process = self._get_job(job_id)
        if process.poll() is not None:
            return
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        with self._lock:
            self._jobs.pop(job_id, None)

    def _get_job(self, job_id: str) -> subprocess.Popen[str]:
        with self._lock:
            process = self._jobs.get(job_id)
        if process is None:
            raise KeyError(f"unknown Codex job: {job_id}")
        return process

    @staticmethod
    def _command_prefix(executable: str) -> list[str]:
        if executable.lower().endswith(".ps1"):
            powershell = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
            return [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", executable]
        return [executable]


class RemoteCodexWorker:
    """Call a Codex worker service over a protected HTTP connection."""

    def __init__(
        self,
        worker_id: str,
        base_url: str,
        token: str,
        *,
        role: WorkerRole = WorkerRole.IMPLEMENTER,
        timeout: float = 10.0,
    ) -> None:
        if not token.strip():
            raise ValueError("remote worker token must not be empty")
        self.worker_id = worker_id
        self.role = role
        self.base_url = base_url.rstrip("/")
        self._token = token
        self.timeout = timeout

    def status(self) -> WorkerStatus:
        try:
            payload = self._request("GET", "/health")
            return WorkerStatus(
                worker_id=self.worker_id,
                role=self.role,
                state=WorkerState(str(payload.get("state", WorkerState.UNAVAILABLE.value))),
                last_heartbeat=payload.get("last_heartbeat"),
                capabilities=tuple(payload.get("capabilities", ())),
                message=str(payload.get("message", "")),
            )
        except (OSError, ValueError, KeyError) as exc:
            return WorkerStatus(self.worker_id, self.role, WorkerState.UNAVAILABLE, message=str(exc))

    def submit(self, task: TechnicalTask, prompt: str) -> str:
        payload = self._request("POST", "/jobs", {"task": task.to_dict(), "prompt": prompt})
        job_id = str(payload.get("job_id", ""))
        if not job_id:
            raise WorkerUnavailable("remote worker returned no job_id")
        return job_id

    def collect_result(self, job_id: str) -> WorkerResult:
        payload = self._request("GET", f"/jobs/{job_id}")
        return WorkerResult(
            job_id=job_id,
            worker_id=self.worker_id,
            state=str(payload.get("state", "failed")),
            exit_code=payload.get("exit_code"),
            stdout=str(payload.get("stdout", "")),
            stderr=str(payload.get("stderr", "")),
        )

    def cancel(self, job_id: str) -> None:
        self._request("DELETE", f"/jobs/{job_id}")

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise OSError(f"remote worker request failed: {exc}") from exc


class CodexWorkerHTTPServer:
    """Small authenticated worker service for a local PC or VPS."""

    def __init__(self, worker: CodexWorker, host: str, port: int, token: str) -> None:
        if not token.strip():
            raise ValueError("worker service token must not be empty")
        self.worker = worker
        self.token = token
        self.server = ThreadingHTTPServer((host, port), self._handler())

    def serve_forever(self) -> None:
        self.server.serve_forever()

    def shutdown(self) -> None:
        self.server.shutdown()

    def _handler(self):
        worker = self.worker
        expected_token = self.token

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def _authorised(self) -> bool:
                return self.headers.get("Authorization", "") == f"Bearer {expected_token}"

            def _send(self, status: int, payload: dict[str, Any]) -> None:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                return json.loads(self.rfile.read(length).decode("utf-8"))

            def do_GET(self) -> None:  # noqa: N802
                if not self._authorised():
                    self._send(401, {"error": "unauthorized"})
                    return
                if self.path == "/health":
                    status = worker.status()
                    self._send(
                        200,
                        {
                            "worker_id": status.worker_id,
                            "state": status.state.value,
                            "last_heartbeat": status.last_heartbeat,
                            "capabilities": list(status.capabilities),
                            "message": status.message,
                        },
                    )
                    return
                if self.path.startswith("/jobs/"):
                    job_id = self.path.rsplit("/", 1)[-1]
                    try:
                        result = worker.collect_result(job_id)
                    except KeyError as exc:
                        self._send(404, {"error": str(exc)})
                        return
                    self._send(200, result.__dict__)
                    return
                self._send(404, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                if not self._authorised():
                    self._send(401, {"error": "unauthorized"})
                    return
                if self.path != "/jobs":
                    self._send(404, {"error": "not found"})
                    return
                try:
                    body = self._json()
                    task = TechnicalTask.from_dict(body["task"])
                    job_id = worker.submit(task, str(body["prompt"]))
                except (KeyError, ValueError, WorkerUnavailable, json.JSONDecodeError) as exc:
                    self._send(400, {"error": str(exc)})
                    return
                self._send(202, {"job_id": job_id})

            def do_DELETE(self) -> None:  # noqa: N802
                if not self._authorised():
                    self._send(401, {"error": "unauthorized"})
                    return
                if not self.path.startswith("/jobs/"):
                    self._send(404, {"error": "not found"})
                    return
                job_id = self.path.rsplit("/", 1)[-1]
                try:
                    worker.cancel(job_id)
                except KeyError as exc:
                    self._send(404, {"error": str(exc)})
                    return
                self._send(200, {"cancelled": True})

        return Handler
