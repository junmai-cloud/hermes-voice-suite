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
    command = calls[0][0]
    assert command[:2] == ["hermes-test", "chat"]
    assert command[2] == "-q"
    assert "会議を始めよう" in command[3]
    assert "未信頼データ" in command[3]
    assert command[4:] == ["-Q", "--source", "tool"]
    assert calls[0][1]["timeout"] == 12
