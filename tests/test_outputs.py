"""Effective output backends (auto_type sugar) — no real I/O."""
from __future__ import annotations

from flm_voice.config import Config
from flm_voice.daemon import Daemon


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
