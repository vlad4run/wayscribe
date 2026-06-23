"""KDE keyboard-layout → language mapping (gdbus subprocess mocked)."""
from __future__ import annotations

import pytest

from wayscribe import keyboard
from wayscribe.config import Config
from wayscribe.daemon import Daemon

_LIST = "([('us', '', 'English (US)'), ('ru', '', 'Russian (typewriter)')],)\n"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("us", "en"),
        ("gb", "en"),
        ("ru", "ru"),
        ("de", "de"),
        ("RU", "ru"),
        ("xyz", None),
        ("", None),
    ],
)
def test_xkb_to_iso(code: str, expected: str | None) -> None:
    assert keyboard._xkb_to_iso(code) == expected


async def test_current_layout_lang_ru(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(method: str, timeout: float = 2.0) -> str:
        return "(uint32 1,)\n" if method == "getLayout" else _LIST

    monkeypatch.setattr(keyboard, "_gdbus", fake)
    assert await keyboard.current_layout_lang() == "ru"


async def test_current_layout_lang_en(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(method: str, timeout: float = 2.0) -> str:
        return "(uint32 0,)\n" if method == "getLayout" else _LIST

    monkeypatch.setattr(keyboard, "_gdbus", fake)
    assert await keyboard.current_layout_lang() == "en"


async def test_current_layout_lang_gdbus_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(method: str, timeout: float = 2.0) -> None:
        return None

    monkeypatch.setattr(keyboard, "_gdbus", fake)
    assert await keyboard.current_layout_lang() is None


async def test_current_layout_lang_index_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(method: str, timeout: float = 2.0) -> str:
        return "(uint32 9,)\n" if method == "getLayout" else _LIST

    monkeypatch.setattr(keyboard, "_gdbus", fake)
    assert await keyboard.current_layout_lang() is None


async def test_set_layout_by_lang_picks_index(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    async def fake(method: str, *args: str, timeout: float = 2.0):
        calls.append((method, args))
        return _LIST if method == "getLayoutsList" else "()\n"

    monkeypatch.setattr(keyboard, "_gdbus", fake)
    assert await keyboard.set_layout_by_lang("ru") is True
    # _LIST is [us, ru] -> ru is index 1.
    assert ("setLayout", ("1",)) in calls


async def test_set_layout_by_lang_missing_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(method: str, *args: str, timeout: float = 2.0):
        return _LIST  # only us/ru installed

    monkeypatch.setattr(keyboard, "_gdbus", fake)
    assert await keyboard.set_layout_by_lang("de") is False


async def test_sync_disabled_keeps_language(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake() -> str:
        return "en"

    monkeypatch.setattr(keyboard, "current_layout_lang", fake)
    daemon = Daemon(Config(language="ru", language_from_layout=False))
    await daemon._sync_language_from_layout()
    assert daemon.cfg.language == "ru"


async def test_sync_enabled_follows_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake() -> str:
        return "en"

    monkeypatch.setattr(keyboard, "current_layout_lang", fake)
    daemon = Daemon(Config(language="ru", language_from_layout=True))
    await daemon._sync_language_from_layout()
    assert daemon.cfg.language == "en"


async def test_sync_enabled_none_keeps_language(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake() -> None:
        return None

    monkeypatch.setattr(keyboard, "current_layout_lang", fake)
    daemon = Daemon(Config(language="ru", language_from_layout=True))
    await daemon._sync_language_from_layout()
    assert daemon.cfg.language == "ru"
