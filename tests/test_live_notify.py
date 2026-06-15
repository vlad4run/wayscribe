"""Daemon live-feedback notification flow (no real notify-send)."""
from __future__ import annotations

import asyncio

import numpy as np
import pytest

from wayscribe import output
from wayscribe.config import Config
from wayscribe.daemon import Daemon, State


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    rec: dict[str, list] = {"update": [], "plain": []}

    def fake_update(title, body="", **kw):
        rec["update"].append((title, body, kw))
        return 99 if kw.get("want_id") else None

    def fake_notify(title, body="", icon="audio-input-microphone"):
        rec["plain"].append((title, body, icon))

    monkeypatch.setattr(output, "notify_update", fake_update)
    monkeypatch.setattr(output, "notify", fake_notify)
    return rec


async def test_first_frame_captures_id(calls: dict[str, list]) -> None:
    d = Daemon(Config(live_notification=True))
    await d._live_notify("wayscribe", "Recording", new_cycle=True)
    assert d._notify_id == 99
    assert calls["update"][0][2]["want_id"] is True


async def test_second_frame_uses_replace_id(calls: dict[str, list]) -> None:
    d = Daemon(Config(live_notification=True))
    await d._live_notify("wayscribe", "Recording", new_cycle=True)
    await d._live_notify("wayscribe", "Recording 0:01", progress=20)
    second = calls["update"][1][2]
    assert second.get("replace_id") == 99
    assert not second.get("want_id")


async def test_capture_failure_falls_back_to_plain(monkeypatch: pytest.MonkeyPatch) -> None:
    plain: list[tuple] = []
    monkeypatch.setattr(output, "notify_update", lambda *a, **kw: None)  # capture fails
    monkeypatch.setattr(
        output, "notify", lambda t, b="", i="audio-input-microphone": plain.append((t, b))
    )
    d = Daemon(Config(live_notification=True))
    await d._live_notify("wayscribe", "Recording", new_cycle=True)  # update -> None
    assert d._notify_supported is False
    await d._live_notify("wayscribe", "next")
    assert ("wayscribe", "next") in plain


async def test_disabled_uses_plain_notify(calls: dict[str, list]) -> None:
    d = Daemon(Config(live_notification=False))
    await d._live_notify("wayscribe", "Recording", new_cycle=True)
    assert calls["plain"] == [("wayscribe", "Recording", "audio-input-microphone")]
    assert calls["update"] == []


async def test_cancel_watchdogs_cancels_notify_task(calls: dict[str, list]) -> None:
    d = Daemon(Config(live_notification=True))
    d.recorder.current_duration = lambda: 1.0  # type: ignore[method-assign]
    d.recorder.peek_recent = lambda s: np.zeros(0, dtype=np.int16)  # type: ignore[method-assign]
    d.state = State.RECORDING
    d._notify_task = asyncio.create_task(d._notify_updater())
    await asyncio.sleep(0)  # let the task reach its first await
    d._cancel_watchdogs()
    assert d._notify_task is None
