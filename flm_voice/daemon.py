"""Long-lived daemon: asyncio Unix-socket server + state machine.

Owns the Recorder, dispatches transcription, and feeds output backends. No
PyQt yet — MVP uses notifications + clipboard only.
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
from enum import Enum
from typing import Any

from flm_voice import output
from flm_voice.config import Config, socket_path
from flm_voice.recorder import Recorder
from flm_voice.transcriber import transcribe_async

log = logging.getLogger("flm-voice")


class State(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"


class Daemon:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.state = State.IDLE
        self.recorder = Recorder(sample_rate=cfg.sample_rate, device=cfg.input_device)
        self._lock: asyncio.Lock | None = None
        self._stop_event: asyncio.Event | None = None
        self._inflight: asyncio.Task[None] | None = None

    def _ensure_async_primitives(self) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()
        if self._stop_event is None:
            self._stop_event = asyncio.Event()

    @property
    def stop_event(self) -> asyncio.Event:
        self._ensure_async_primitives()
        assert self._stop_event is not None
        return self._stop_event

    async def handle_command(self, cmd: str) -> dict[str, Any]:
        self._ensure_async_primitives()
        assert self._lock is not None
        async with self._lock:
            if cmd == "status":
                return {"ok": True, "state": self.state.value}

            if cmd == "stop":
                self.stop_event.set()
                return {"ok": True, "state": self.state.value, "stopping": True}

            if cmd == "cancel":
                if self.state == State.RECORDING:
                    await asyncio.to_thread(self.recorder.stop)
                    self.state = State.IDLE
                    output.notify("flm-voice", "cancelled")
                return {"ok": True, "state": self.state.value}

            if cmd == "toggle":
                if self.state == State.IDLE:
                    return await self._start_recording()
                if self.state == State.RECORDING:
                    return await self._stop_and_dispatch()
                output.notify("flm-voice", "still transcribing previous recording…")
                return {"ok": False, "state": self.state.value, "reason": "busy"}

            return {"ok": False, "error": f"unknown command: {cmd}"}

    async def _start_recording(self) -> dict[str, Any]:
        try:
            await asyncio.to_thread(self.recorder.start)
        except Exception as exc:
            log.exception("recorder failed to start")
            output.notify("flm-voice", f"mic error: {exc}", icon="dialog-error")
            return {"ok": False, "error": str(exc)}
        self.state = State.RECORDING
        output.notify("flm-voice", "recording…", icon="audio-input-microphone")
        return {"ok": True, "state": self.state.value}

    async def _stop_and_dispatch(self) -> dict[str, Any]:
        wav = await asyncio.to_thread(self.recorder.stop)
        self.state = State.TRANSCRIBING
        self._inflight = asyncio.create_task(self._transcribe_and_output(wav))
        return {"ok": True, "state": self.state.value, "bytes": len(wav)}

    async def _transcribe_and_output(self, wav: bytes) -> None:
        try:
            text = await transcribe_async(wav, self.cfg)
        except Exception as exc:
            log.exception("transcription failed")
            output.notify("flm-voice", f"transcription failed: {exc}", icon="dialog-error")
            self.state = State.IDLE
            return
        text = (text or "").strip()
        if not text:
            output.notify("flm-voice", "(empty transcription)")
            self.state = State.IDLE
            return
        for backend in self.cfg.outputs:
            try:
                if backend == "clipboard":
                    output.to_clipboard(text)
                elif backend == "type":
                    output.type_text(text)
                elif backend == "notify":
                    preview = text if len(text) < 200 else text[:197] + "…"
                    output.notify("flm-voice", preview)
            except Exception:
                log.exception("output backend %r failed", backend)
        log.info("transcribed %d chars", len(text))
        self.state = State.IDLE


async def _client_handler(
    daemon: Daemon,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    try:
        line = await reader.readline()
        if not line:
            return
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            resp: dict[str, Any] = {"ok": False, "error": f"bad json: {exc}"}
        else:
            resp = await daemon.handle_command(msg.get("cmd", ""))
    except Exception as exc:
        log.exception("handler error")
        resp = {"ok": False, "error": str(exc)}
    try:
        writer.write(json.dumps(resp).encode() + b"\n")
        await writer.drain()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def _serve(daemon: Daemon) -> None:
    sock = socket_path()
    sock.parent.mkdir(parents=True, exist_ok=True)
    if sock.exists():
        sock.unlink()

    server = await asyncio.start_unix_server(
        lambda r, w: _client_handler(daemon, r, w),
        path=str(sock),
    )
    log.info("listening on %s", sock)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, daemon.stop_event.set)

    try:
        async with server:
            await daemon.stop_event.wait()
    finally:
        if daemon.recorder.is_recording:
            await asyncio.to_thread(daemon.recorder.stop)
        sock.unlink(missing_ok=True)
        log.info("daemon exited")


def run() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = Config.load()
    daemon = Daemon(cfg)
    try:
        asyncio.run(_serve(daemon))
    except KeyboardInterrupt:
        return 0
    return 0
