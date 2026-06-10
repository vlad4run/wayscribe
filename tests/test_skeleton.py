"""Sanity checks: package imports cleanly, CLI builds, IPC fails gracefully."""
from __future__ import annotations

import pytest


def test_package_imports() -> None:
    from wayscribe import (  # noqa: F401
        config,
        daemon,
        ipc,
        keyboard,
        output,
        recorder,
        transcriber,
        vad,
    )


def test_cli_help_does_not_crash(capsys: pytest.CaptureFixture[str]) -> None:
    from wayscribe.__main__ import build_parser

    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--help"])
    assert exc.value.code == 0
    assert "wayscribe" in capsys.readouterr().out


def test_ipc_returns_2_when_no_daemon(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "wayscribe.ipc.socket_path", lambda: tmp_path / "missing.sock"
    )
    from wayscribe.ipc import send_command

    assert send_command("status") == 2
