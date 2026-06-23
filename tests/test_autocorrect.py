"""Phase-2 autocorrect pure core (WordBuffer, decide) + command gate/toggle.

No evdev: only the layout-agnostic logic is exercised here. The live grab loop
needs real /dev/input and is verified on hardware.
"""
from __future__ import annotations

import asyncio

import pytest

from wayscribe import autocorrect
from wayscribe.autocorrect import SPACE, WordBuffer, decide
from wayscribe.config import Config
from wayscribe.daemon import Daemon

# Reverse map: US glyph -> evdev keycode (unshifted), for typing test words.
_CHAR_CODE = {lo: code for code, (lo, _hi) in autocorrect.KEYCODE_CHARS.items()}
_BACKSPACE = autocorrect.BACKSPACE
_ENTER = autocorrect.ENTER


def _type(buf: WordBuffer, text: str, shift: bool = False) -> str | None:
    out = None
    for ch in text:
        out = buf.feed(_CHAR_CODE[ch], shift)
    return out


# --- WordBuffer -----------------------------------------------------------


def test_buffer_returns_raw_word_on_space() -> None:
    buf = WordBuffer()
    assert _type(buf, "ghbdtn") is None  # no boundary yet
    assert buf.feed(SPACE, False) == "ghbdtn"


def test_buffer_shift_gives_uppercase() -> None:
    buf = WordBuffer()
    buf.feed(_CHAR_CODE["g"], shift=True)
    _type(buf, "hbdtn")
    assert buf.feed(SPACE, False) == "Ghbdtn"


def test_buffer_backspace_pops() -> None:
    buf = WordBuffer()
    _type(buf, "ghx")
    buf.feed(_BACKSPACE, False)
    _type(buf, "bdtn")
    assert buf.feed(SPACE, False) == "ghbdtn"


def test_buffer_enter_resets_without_word() -> None:
    buf = WordBuffer()
    _type(buf, "ghbdtn")
    assert buf.feed(_ENTER, False) is None
    assert buf.feed(SPACE, False) is None  # buffer was cleared


# --- decide (layout-aware) ------------------------------------------------


def test_decide_latin_active_meant_russian() -> None:
    c = decide("ghbdtn", "en", 0.15)
    assert c is not None
    assert c.text == "привет " and c.backspaces == 7
    assert c.target == "ru" and c.original == "ghbdtn"


def test_decide_russian_active_meant_english() -> None:
    # RU layout active: physical "hello" keys produced "руддщ" on screen.
    c = decide("hello", "ru", 0.15)
    assert c is not None
    assert c.text == "hello " and c.original == "руддщ"
    assert c.target == "en"


def test_decide_correct_english_is_noop() -> None:
    assert decide("hello", "en", 0.15) is None


def test_decide_correct_russian_is_noop() -> None:
    # RU active, physical "ghbdtn" -> "привет" on screen: already correct.
    assert decide("ghbdtn", "ru", 0.15) is None


# --- command gate / toggle ------------------------------------------------


async def test_autocorrect_disabled_in_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("wayscribe.output.notify", lambda *a, **k: None)
    daemon = Daemon(Config(evdev_autocorrect=False))
    reply = await daemon.handle_command({"cmd": "autocorrect", "value": "on"})
    assert not reply["ok"] and reply["reason"] == "autocorrect-disabled"


async def test_autocorrect_toggle_on_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("wayscribe.output.notify", lambda *a, **k: None)

    class FakeEngine:
        def __init__(self, cfg) -> None:
            pass

        async def run(self) -> None:
            await asyncio.Event().wait()  # block until cancelled

    monkeypatch.setattr(autocorrect, "AutocorrectEngine", FakeEngine)
    daemon = Daemon(Config(evdev_autocorrect=True))

    on = await daemon.handle_command({"cmd": "autocorrect", "value": "toggle"})
    assert on["autocorrect"] == "on"
    off = await daemon.handle_command({"cmd": "autocorrect", "value": "toggle"})
    assert off["autocorrect"] == "off"
