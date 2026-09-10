from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


_MODULE_PATH = Path(__file__).parents[1] / "scripts" / "local_codex_worker_supervisor.py"
_SPEC = spec_from_file_location("local_codex_worker_supervisor", _MODULE_PATH)
worker_supervisor = module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(worker_supervisor)

_TUNNEL_MODULE_PATH = Path(__file__).parents[1] / "scripts" / "local_codex_tunnel_supervisor.py"
_TUNNEL_SPEC = spec_from_file_location("local_codex_tunnel_supervisor", _TUNNEL_MODULE_PATH)
tunnel_supervisor = module_from_spec(_TUNNEL_SPEC)
assert _TUNNEL_SPEC.loader is not None
_TUNNEL_SPEC.loader.exec_module(tunnel_supervisor)


def test_worker_supervisor_waits_when_env_file_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(worker_supervisor, "ENV_FILE", tmp_path / ".env")
    assert worker_supervisor.load_token() is None


def test_worker_supervisor_reads_only_dedicated_token_key(tmp_path, monkeypatch):
    env_file = Path(tmp_path) / ".env"
    env_file.write_text(
        "OTHER_SECRET=do-not-use\nCODEX_WORKER_TOKEN='test-worker-token'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(worker_supervisor, "ENV_FILE", env_file)
    assert worker_supervisor.load_token() == "test-worker-token"


def test_worker_supervisor_ignores_empty_token(tmp_path, monkeypatch):
    env_file = Path(tmp_path) / ".env"
    env_file.write_text("CODEX_WORKER_TOKEN=\n", encoding="utf-8")
    monkeypatch.setattr(worker_supervisor, "ENV_FILE", env_file)
    assert worker_supervisor.load_token() is None


def test_tunnel_supervisor_does_not_run_ssh_without_config(tmp_path, monkeypatch):
    monkeypatch.setattr(tunnel_supervisor, "SSH_CONFIG", str(tmp_path / "missing"))
    monkeypatch.setattr(
        tunnel_supervisor.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("ssh invoked")),
    )
    assert tunnel_supervisor.ssh_config_ready() is False


def test_tunnel_retry_uses_capped_exponential_backoff(monkeypatch):
    monkeypatch.setattr(tunnel_supervisor, "RETRY_SECONDS", 60)
    monkeypatch.setattr(tunnel_supervisor, "MAX_RETRY_SECONDS", 3600)
    assert tunnel_supervisor.retry_delay(1) == 60
    assert tunnel_supervisor.retry_delay(2) == 120
    assert tunnel_supervisor.retry_delay(20) == 3600
