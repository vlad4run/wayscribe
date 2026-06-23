"""Configuration loaded from $XDG_CONFIG_HOME/wayscribe/config.toml."""
from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "wayscribe"


def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/wayscribe-{os.getuid()}"
    return Path(base)


def socket_path() -> Path:
    return runtime_dir() / "wayscribe.sock"


@dataclass
class Config:
    endpoint: str = "http://localhost:52625"
    model: str = "whisper-v3:turbo"
    request_timeout_sec: float = 60.0
    language: str | None = "ru"
    language_from_layout: bool = True
    languages: list[str] = field(default_factory=lambda: ["ru", "en"])
    sample_rate: int = 16000
    input_device: str | None = None
    outputs: list[str] = field(default_factory=lambda: ["clipboard", "notify"])
    auto_type: bool = False  # also type the transcript into the focused window
    # one in-place-updated notification (recording bar + status) instead of
    # discrete popups; degrades to discrete popups where unsupported
    live_notification: bool = True
    # Phase-6 polish
    max_duration_sec: float = 300.0
    warmup: bool = True
    auto_stop: bool = False
    auto_stop_silence_sec: float = 1.5
    auto_stop_min_record_sec: float = 0.8
    vad_rms_threshold: float = 500.0
    # Layout fixer (ghbdtn -> привет)
    fix_source: str = "selection"  # "selection" | "last_word"
    fix_last_word_count: int = 1
    switch_layout: bool = False  # also flip the active KDE layout after a fix
    trigram_confidence_min: float = 0.15  # below this, defer to the LLM (if enabled)
    # LLM (chat) — separate from the STT endpoint above
    llm_endpoint: str = ""  # empty disables all LLM features
    llm_model: str = ""
    llm_api_key: str = ""
    llm_timeout_sec: float = 30.0
    # Phase 2 (opt-in, security-sensitive): global evdev autocorrect
    evdev_autocorrect: bool = False

    @classmethod
    def load(cls) -> Config:
        path = config_dir() / "config.toml"
        if not path.exists():
            return cls()
        with path.open("rb") as f:
            data = tomllib.load(f)
        fields = cls.__dataclass_fields__
        unknown = sorted(set(data) - set(fields))
        if unknown:
            log.warning("ignoring unknown config keys in %s: %s", path, unknown)
        return cls(**{k: v for k, v in data.items() if k in fields})
