from pathlib import Path

from voice_suite.adapters import HermesCliBrain


def test_hermes_brain_builds_injected_command(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return type("Result", (), {"returncode": 0, "stdout": "返答", "stderr": ""})()

    monkeypatch.setattr("voice_suite.adapters.subprocess.run", fake_run)
    brain = HermesCliBrain(command="hermes-test", timeout=12)
    assert brain.answer("会議を始めよう") == "返答"
    assert calls[0][0] == ["hermes-test", "chat", "-q", "会議を始めよう", "-Q", "--source", "tool"]
    assert calls[0][1]["timeout"] == 12
