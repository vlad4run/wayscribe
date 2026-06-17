"""Effective output backends (auto_type sugar) — no real I/O."""
from __future__ import annotations

import pytest

from wayscribe import output
from wayscribe.config import Config
from wayscribe.daemon import Daemon


def _force_ydotool(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Pin the type_text path to ydotool and record every subprocess argv."""
    calls: list[list[str]] = []

    def fake_which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name == "ydotool" else None

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        return None

    monkeypatch.setattr(output.shutil, "which", fake_which)
    monkeypatch.setattr(output.subprocess, "run", fake_run)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    return calls


def test_type_text_ascii_uses_ydotool_type(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _force_ydotool(monkeypatch)
    output.type_text("hello, world.")
    assert calls == [["ydotool", "type", "--", "hello, world."]]


def test_type_text_non_ascii_pastes_via_clipboard(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _force_ydotool(monkeypatch)
    output.type_text("привет, мир.")
    # First wl-copy stuffs the clipboard, then ydotool synthesizes Ctrl+V.
    assert calls == [
        ["wl-copy"],
        ["ydotool", "key", "29:1", "47:1", "47:0", "29:0"],
    ]


def test_auto_type_off_keeps_outputs() -> None:
    daemon = Daemon(Config(outputs=["clipboard", "notify"], auto_type=False))
    assert daemon._effective_outputs() == ["clipboard", "notify"]


def test_auto_type_on_appends_type() -> None:
    daemon = Daemon(Config(outputs=["clipboard", "notify"], auto_type=True))
    assert daemon._effective_outputs() == ["clipboard", "notify", "type"]


def test_auto_type_on_no_duplicate_when_already_listed() -> None:
    daemon = Daemon(Config(outputs=["type", "notify"], auto_type=True))
    assert daemon._effective_outputs() == ["type", "notify"]


def test_effective_outputs_does_not_mutate_config() -> None:
    cfg = Config(outputs=["clipboard"], auto_type=True)
    daemon = Daemon(cfg)
    daemon._effective_outputs()
    assert cfg.outputs == ["clipboard"]
