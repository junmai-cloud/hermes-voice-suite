from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


_MODULE_PATH = Path(__file__).parents[1] / "scripts" / "local_codex_worker_supervisor.py"
_SPEC = spec_from_file_location("local_codex_worker_supervisor", _MODULE_PATH)
worker_supervisor = module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(worker_supervisor)


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
