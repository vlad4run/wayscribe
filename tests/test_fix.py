"""`fix` / `translate` IPC commands in the daemon (subprocess I/O mocked)."""
from __future__ import annotations

import pytest

from wayscribe import llm, output, selection
from wayscribe.config import Config
from wayscribe.daemon import Daemon, State


@pytest.fixture
def _mute_notify(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(output, "notify", lambda *a, **k: None)


def _capture(monkeypatch: pytest.MonkeyPatch, text: str) -> list[str]:
    """Stub selection capture to `text`; return list that records write-backs."""
    written: list[str] = []
    monkeypatch.setattr(selection, "capture_target", lambda source, n: text)
    monkeypatch.setattr(selection, "replace_with", lambda t: written.append(t))
    return written


async def test_fix_rekeys_wrong_layout(monkeypatch: pytest.MonkeyPatch, _mute_notify) -> None:
    written = _capture(monkeypatch, "ghbdtn")
    daemon = Daemon(Config())
    reply = await daemon.handle_command({"cmd": "fix"})
    assert reply["ok"] and reply["changed"]
    assert written == ["привет"]


async def test_fix_leaves_correct_text_alone(
    monkeypatch: pytest.MonkeyPatch, _mute_notify
) -> None:
    written = _capture(monkeypatch, "hello")
    daemon = Daemon(Config())  # LLM disabled by default
    reply = await daemon.handle_command({"cmd": "fix"})
    assert reply["ok"] and not reply["changed"]
    assert written == []


async def test_fix_empty_selection(monkeypatch: pytest.MonkeyPatch, _mute_notify) -> None:
    _capture(monkeypatch, "")
    daemon = Daemon(Config())
    reply = await daemon.handle_command({"cmd": "fix"})
    assert not reply["ok"] and reply["reason"] == "empty"


async def test_fix_busy_when_not_idle(monkeypatch: pytest.MonkeyPatch, _mute_notify) -> None:
    _capture(monkeypatch, "ghbdtn")
    daemon = Daemon(Config())
    daemon.state = State.TRANSCRIBING
    reply = await daemon.handle_command({"cmd": "fix"})
    assert not reply["ok"] and reply["reason"] == "busy"


async def test_translate_disabled_without_llm(
    monkeypatch: pytest.MonkeyPatch, _mute_notify
) -> None:
    _capture(monkeypatch, "привет")
    daemon = Daemon(Config())  # no llm_endpoint
    reply = await daemon.handle_command({"cmd": "translate"})
    assert not reply["ok"] and reply["reason"] == "llm-disabled"


async def test_translate_writes_back(monkeypatch: pytest.MonkeyPatch, _mute_notify) -> None:
    written = _capture(monkeypatch, "привет")

    async def fake_translate(text: str, cfg) -> str:
        return "hello"

    monkeypatch.setattr(llm, "translate_to_en", fake_translate)
    daemon = Daemon(Config(llm_endpoint="http://x", llm_model="m"))
    reply = await daemon.handle_command({"cmd": "translate"})
    assert reply["ok"] and reply["changed"]
    assert written == ["hello"]
