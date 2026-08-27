from __future__ import annotations

import json
import io
import os
import subprocess
import threading
import urllib.error
import urllib.request
from http.client import HTTPResponse

import pytest

from voice_suite.codex_chat import (
    ChatWorkerConfig,
    ChatWorkerHTTPServer,
    ChatWorkerTimeout,
    ChatWorkerUnavailable,
    CodexReadOnlyChatWorker,
)


class FakeProcess:
    def __init__(self, stdout: bytes = b"answer", returncode: int = 0, stderr: bytes = b""):
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def wait(self):
        return self.returncode

    def kill(self):
        self.returncode = -9


def test_build_command_always_uses_read_only(monkeypatch):
    monkeypatch.setattr("voice_suite.codex_chat.shutil.which", lambda _name: "/usr/bin/codex")
    worker = CodexReadOnlyChatWorker(
        ChatWorkerConfig(command="codex", working_directory="/tmp", timeout_seconds=3)
    )

    command = worker.build_command("状態を教えて")

    assert command == [
        "/usr/bin/codex",
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--",
        "状態を教えて",
    ]
    assert "workspace-write" not in command


def test_build_command_handles_windows_codex_cmd_shim(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "voice_suite.codex_chat.shutil.which",
        lambda name: "C:\\Users\\test\\AppData\\Roaming\\npm\\codex.CMD",
    )
    worker = CodexReadOnlyChatWorker(ChatWorkerConfig(working_directory=tmp_path))
    command = worker.build_command("確認")
    assert command[0] == "C:\\Users\\test\\AppData\\Roaming\\npm\\codex.CMD"
    assert command[-4:] == ["--sandbox", "read-only", "--", "確認"]


def test_answer_passes_only_prompt_and_read_only_sandbox(monkeypatch, tmp_path):
    calls: list[dict] = []
    monkeypatch.setattr("voice_suite.codex_chat.shutil.which", lambda _name: "/usr/bin/codex")

    def fake_popen(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return FakeProcess(stdout="  日本語の回答  ".encode())

    monkeypatch.setattr("voice_suite.codex_chat.subprocess.Popen", fake_popen)
    worker = CodexReadOnlyChatWorker(ChatWorkerConfig(working_directory=tmp_path))

    assert worker.answer("  状態を教えて  ") == "日本語の回答"
    assert calls[0]["command"][-4:] == ["--sandbox", "read-only", "--", "状態を教えて"]
    assert calls[0]["cwd"] == str(tmp_path)
    assert calls[0]["stdin"] is subprocess.DEVNULL
    assert calls[0]["env"]["PATH"] == os.environ["PATH"] if "PATH" in os.environ else True
    assert "CODEX_CHAT_WORKER_TOKEN" not in calls[0]["env"]


def test_answer_redacts_known_secrets_and_rejects_missing_workdir(monkeypatch, tmp_path):
    monkeypatch.setattr("voice_suite.codex_chat.shutil.which", lambda _name: "/usr/bin/codex")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret-value")
    monkeypatch.setenv("CODEX_CHAT_WORKER_TOKEN", "worker-secret-value")
    monkeypatch.setattr(
        "voice_suite.codex_chat.subprocess.Popen",
        lambda *_args, **_kwargs: FakeProcess(
            stdout=b"answer openai-secret-value worker-secret-value"
        ),
    )

    worker = CodexReadOnlyChatWorker(ChatWorkerConfig(working_directory=tmp_path))
    assert worker.answer("確認") == "answer [redacted] [redacted]"

    missing = CodexReadOnlyChatWorker(
        ChatWorkerConfig(working_directory=tmp_path / "does-not-exist")
    )
    with pytest.raises(ChatWorkerUnavailable, match="working directory"):
        missing.answer("確認")


def test_answer_rejects_unbounded_codex_output(monkeypatch, tmp_path):
    monkeypatch.setattr("voice_suite.codex_chat.shutil.which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(
        "voice_suite.codex_chat.subprocess.Popen",
        lambda *_args, **_kwargs: FakeProcess(stdout=b"x" * 5000),
    )

    worker = CodexReadOnlyChatWorker(
        ChatWorkerConfig(working_directory=tmp_path, max_response_chars=10)
    )
    with pytest.raises(ChatWorkerUnavailable, match="output exceeded"):
        worker.answer("確認")


def test_empty_and_non_string_prompts_are_rejected(monkeypatch):
    monkeypatch.setattr("voice_suite.codex_chat.shutil.which", lambda _name: "/usr/bin/codex")
    worker = CodexReadOnlyChatWorker()

    with pytest.raises(ValueError, match="must not be empty"):
        worker.build_command("  ")
    with pytest.raises(ValueError, match="must be a string"):
        worker.build_command(123)  # type: ignore[arg-type]


def test_timeout_is_reported_without_retry(monkeypatch):
    monkeypatch.setattr("voice_suite.codex_chat.shutil.which", lambda _name: "/usr/bin/codex")
    class HangingProcess(FakeProcess):
        def __init__(self):
            super().__init__(returncode=None)

        def poll(self):
            return self.returncode

    monkeypatch.setattr(
        "voice_suite.codex_chat.subprocess.Popen",
        lambda *_args, **_kwargs: HangingProcess(),
    )

    with pytest.raises(ChatWorkerTimeout):
        CodexReadOnlyChatWorker(ChatWorkerConfig(timeout_seconds=0.01)).answer("確認")


def _start_server(monkeypatch):
    monkeypatch.setattr("voice_suite.codex_chat.shutil.which", lambda _name: "/usr/bin/codex")
    worker = CodexReadOnlyChatWorker()
    server = ChatWorkerHTTPServer(worker, "127.0.0.1", 0, "test-chat-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _request(server, method: str, path: str, payload=None, token: str = "test-chat-token"):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server.server_port}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_http_api_accepts_prompt_only_and_rejects_task_fields(monkeypatch):
    server, thread = _start_server(monkeypatch)
    try:
        monkeypatch.setattr(
            "voice_suite.codex_chat.subprocess.Popen",
            lambda *_a, **_k: FakeProcess(stdout=b"ok"),
        )
        status, body = _request(server, "POST", "/chat", {"prompt": "こんにちは"})
        assert status == 200
        assert body == {"response": "ok"}

        status, body = _request(
            server,
            "POST",
            "/chat",
            {"prompt": "変更して", "task": {"operation": "deploy"}},
        )
        assert status == 400
        assert "only the prompt field" in body["error"]
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_http_api_requires_authentication(monkeypatch):
    server, thread = _start_server(monkeypatch)
    try:
        status, body = _request(server, "GET", "/health", token="wrong")
        assert status == 401
        assert body == {"error": "unauthorized"}
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
