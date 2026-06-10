"""Backend probe parsing, doctor checks, and status backend reporting."""
from __future__ import annotations

import pytest

from wayscribe import doctor
from wayscribe.config import Config
from wayscribe.transcriber import BackendHealth, _parse_models


def test_parse_models_extracts_ids() -> None:
    payload = {"data": [{"id": "whisper-v3:turbo"}, {"id": "other"}, {"no": "id"}]}
    assert _parse_models(payload) == ["whisper-v3:turbo", "other"]


def test_parse_models_handles_garbage() -> None:
    assert _parse_models(None) == []
    assert _parse_models({"data": "nope"}) == []
    assert _parse_models({}) == []


def test_backend_health_has_model_prefix_match() -> None:
    h = BackendHealth(True, ["whisper-v3:turbo"])
    assert h.has_model("whisper-v3:turbo")
    assert h.has_model("whisper-v3")  # prefix
    assert not h.has_model("llama")


def test_backend_checks_down_reports_two_failures(monkeypatch) -> None:
    monkeypatch.setattr(
        doctor, "probe_sync", lambda cfg: BackendHealth(False, detail="refused")
    )
    checks = doctor._backend_checks(Config())
    assert [c.ok for c in checks] == [False, False]
    assert "refused" in checks[0].detail


def test_backend_checks_up_with_model(monkeypatch) -> None:
    cfg = Config(model="whisper-v3:turbo")
    monkeypatch.setattr(
        doctor, "probe_sync", lambda c: BackendHealth(True, ["whisper-v3:turbo"])
    )
    checks = doctor._backend_checks(cfg)
    assert [c.ok for c in checks] == [True, True]


def test_tool_checks_type_optional_when_not_wanted(monkeypatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _: None)
    cfg = Config(outputs=["clipboard", "notify"], auto_type=False)
    by_label = {c.label: c for c in doctor._tool_checks(cfg)}
    assert by_label["wtype/ydotool"].required is False
    assert by_label["wl-copy"].required is True


def test_tool_checks_type_required_when_auto_type(monkeypatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _: None)
    cfg = Config(outputs=["clipboard"], auto_type=True)
    by_label = {c.label: c for c in doctor._tool_checks(cfg)}
    assert by_label["wtype/ydotool"].required is True


def test_run_exit_1_when_backend_down(monkeypatch, capsys) -> None:
    monkeypatch.setattr(Config, "load", classmethod(lambda cls: Config()))
    monkeypatch.setattr(
        doctor, "probe_sync", lambda cfg: BackendHealth(False, detail="refused")
    )
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/" + name)

    def _raise(*a, **k):
        raise doctor.DaemonUnreachable("x")

    monkeypatch.setattr(doctor, "query", _raise)
    assert doctor.run() == 1
    out = capsys.readouterr().out
    assert "backend" in out and "✗" in out


@pytest.mark.asyncio
async def test_status_reports_backend(monkeypatch) -> None:
    from wayscribe import daemon as daemon_mod
    from wayscribe.daemon import Daemon
    from wayscribe.transcriber import BackendHealth as BH

    async def fake_probe(cfg, timeout=2.0):
        return BH(True, ["whisper-v3:turbo"])

    monkeypatch.setattr(daemon_mod, "probe_async", fake_probe)
    d = Daemon(Config())
    reply = await d.handle_command({"cmd": "status"})
    assert reply["backend"] == "up"
    assert reply["endpoint"] == Config().endpoint
