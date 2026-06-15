"""output.py notification primitives + type_text wtype→ydotool fallback.

No real subprocesses: subprocess.run and shutil.which are monkeypatched.
"""
from __future__ import annotations

import subprocess

import pytest

from wayscribe import output


class _FakeRun:
    def __init__(self, stdout: str = "", returncode: int = 0, raises: Exception | None = None):
        self.calls: list[tuple[list[str], dict]] = []
        self._stdout = stdout
        self._returncode = returncode
        self._raises = raises

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if self._raises is not None:
            raise self._raises
        return subprocess.CompletedProcess(argv, self._returncode, stdout=self._stdout, stderr="")


def test_send_notification_builds_argv_with_hints(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRun(stdout="42")
    monkeypatch.setattr(output.subprocess, "run", fake)
    nid = output._send_notification(
        "wayscribe",
        "body",
        icon="media-record",
        replace_id=7,
        progress=55,
        timeout_ms=0,
        capture_id=True,
    )
    assert nid == 42
    argv, kwargs = fake.calls[0]
    assert argv[0] == "notify-send"
    assert "--replace-id" in argv and "7" in argv
    assert "int:value:55" in argv
    assert "--expire-time" in argv and "0" in argv
    assert "--print-id" in argv
    assert argv[-2:] == ["wayscribe", "body"]
    assert kwargs.get("capture_output") is True


def test_send_notification_no_optional_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRun()
    monkeypatch.setattr(output.subprocess, "run", fake)
    assert output._send_notification("t", "b") is None
    argv, _ = fake.calls[0]
    assert "--print-id" not in argv
    assert "--replace-id" not in argv
    assert "--hint" not in argv
    assert "--expire-time" not in argv


def test_send_notification_garbage_id_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(output.subprocess, "run", _FakeRun(stdout="not-an-int"))
    assert output._send_notification("t", capture_id=True) is None


def test_send_notification_nonzero_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(output.subprocess, "run", _FakeRun(stdout="9", returncode=1))
    assert output._send_notification("t", capture_id=True) is None


def test_send_notification_missing_binary_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(output.subprocess, "run", _FakeRun(raises=FileNotFoundError()))
    assert output._send_notification("t", capture_id=True) is None
    assert output._send_notification("t") is None  # no raise


def test_notify_update_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(output.subprocess, "run", _FakeRun(stdout="5"))
    assert output.notify_update("t", "b", want_id=True) == 5


def _which(present: set[str]):
    return lambda tool: f"/usr/bin/{tool}" if tool in present else None


def test_type_text_falls_back_to_ydotool_when_wtype_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(output.shutil, "which", _which({"wtype", "ydotool"}))
    calls: list[str] = []

    def fake_run(argv, **kw):
        calls.append(argv[0])
        if argv[0] == "wtype":
            raise subprocess.CalledProcessError(1, argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(output.subprocess, "run", fake_run)
    output.type_text("hi")
    assert calls == ["wtype", "ydotool"]


def test_type_text_wtype_only_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(output.shutil, "which", _which({"wtype"}))

    def fake_run(argv, **kw):
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(output.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="ydotool"):
        output.type_text("hi")


def test_type_text_ydotool_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(output.shutil, "which", _which({"ydotool"}))
    calls: list[str] = []
    monkeypatch.setattr(
        output.subprocess,
        "run",
        lambda argv, **kw: calls.append(argv[0]) or subprocess.CompletedProcess(argv, 0),
    )
    output.type_text("hi")
    assert calls == ["ydotool"]


def test_type_text_no_tools_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(output.shutil, "which", _which(set()))
    with pytest.raises(RuntimeError):
        output.type_text("hi")
