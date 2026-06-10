"""`wayscribe doctor`: one-shot self-diagnosis checklist.

Standalone — does not need the daemon for tool/config/backend checks; it
queries the daemon only to report whether it is running. Each line is a
check with a ✓/✗ mark. Exit code is non-zero if any required check fails,
so it is usable in scripts.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass

from wayscribe.config import Config, config_dir
from wayscribe.ipc import DaemonUnreachable, query
from wayscribe.transcriber import probe_sync

OK = "✓"
BAD = "✗"
WARN = "!"


@dataclass
class Check:
    label: str
    ok: bool
    detail: str = ""
    required: bool = True


def _daemon_check() -> Check:
    try:
        reply = query("status", timeout=3.0)
    except DaemonUnreachable:
        return Check(
            "daemon",
            False,
            "not running — systemctl --user start wayscribe",
            required=False,
        )
    except OSError as exc:
        return Check("daemon", False, f"ipc error: {exc}", required=False)
    return Check("daemon", True, f"running ({reply.get('state', '?')})", required=False)


def _backend_checks(cfg: Config) -> list[Check]:
    health = probe_sync(cfg)
    if not health.reachable:
        return [
            Check("backend", False, f"unreachable {cfg.endpoint} — {health.detail}"),
            Check(f"model {cfg.model}", False, "backend down"),
        ]
    # /v1/models lists the LLM catalog; ASR (whisper) models do not appear there,
    # so absence is not a failure — keep this line informational only.
    advertised = health.has_model(cfg.model)
    return [
        Check("backend", True, cfg.endpoint),
        Check(
            f"model {cfg.model}",
            advertised,
            "advertised" if advertised else "not advertised (normal for ASR) — "
            "confirm with: wayscribe oneshot --duration 3",
            required=False,
        ),
    ]


def _tool_checks(cfg: Config) -> list[Check]:
    outputs = set(cfg.outputs)
    wants_type = cfg.auto_type or "type" in outputs
    checks: list[Check] = []

    if "clipboard" in outputs:
        present = shutil.which("wl-copy") is not None
        checks.append(
            Check("wl-copy", present, "" if present else "install wl-clipboard")
        )

    typer = shutil.which("wtype") or shutil.which("ydotool")
    checks.append(
        Check(
            "wtype/ydotool",
            typer is not None,
            (typer or "install wtype") if wants_type else "not needed",
            required=wants_type,
        )
    )

    notify = shutil.which("notify-send") is not None
    checks.append(
        Check("notify-send", notify, "" if notify else "install libnotify-tools",
              required="notify" in outputs)
    )
    return checks


def _config_check() -> Check:
    path = config_dir() / "config.toml"
    if path.exists():
        return Check("config", True, str(path))
    return Check("config", True, "using defaults (no config.toml)", required=False)


def run() -> int:
    cfg = Config.load()
    checks = [
        _daemon_check(),
        *_backend_checks(cfg),
        *_tool_checks(cfg),
        _config_check(),
    ]
    width = max(len(c.label) for c in checks)
    for c in checks:
        mark = OK if c.ok else (BAD if c.required else WARN)
        line = f"  {c.label.ljust(width)}  {mark}"
        if c.detail:
            line += f"  {c.detail}"
        print(line)

    failed = [c for c in checks if c.required and not c.ok]
    return 1 if failed else 0
