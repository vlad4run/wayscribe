"""Long-lived daemon: asyncio Unix-socket server + state machine.

Owns the Recorder, dispatches transcription, and feeds output backends
(clipboard / keystroke synthesis / KDE notifications). Headless — no GUI.
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
from enum import StrEnum
from typing import Any

import httpx

from wayscribe import keyboard, llm, output, selection, vad
from wayscribe.config import Config, socket_path
from wayscribe.recorder import Recorder, silent_wav
from wayscribe.transcriber import probe_async, transcribe_async

log = logging.getLogger("wayscribe")

# RMS that maps to a full (100%) mic-level bar during recording. int16 speech
# peaks well below this; tuned so normal talking lands mid-bar.
_LEVEL_FULL_SCALE = 3000.0


def _fmt_mmss(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


class State(StrEnum):
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
        self._max_duration_task: asyncio.Task[None] | None = None
        self._vad_task: asyncio.Task[None] | None = None
        # Live-feedback notification: one popup updated in place across the
        # record→transcribe→done cycle. `_notify_id` is the current popup id;
        # `_notify_supported` flips False if id capture fails (degrade to plain).
        self._notify_id: int | None = None
        self._notify_supported: bool = True
        self._notify_task: asyncio.Task[None] | None = None
        # Phase-2 global autocorrect: None = off; a live task = grab active.
        self._autocorrect_task: asyncio.Task[None] | None = None

    def _ensure_async_primitives(self) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()
        if self._stop_event is None:
            self._stop_event = asyncio.Event()

    @property
    def lock(self) -> asyncio.Lock:
        self._ensure_async_primitives()
        assert self._lock is not None
        return self._lock

    @property
    def stop_event(self) -> asyncio.Event:
        self._ensure_async_primitives()
        assert self._stop_event is not None
        return self._stop_event

    def _status_snapshot(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        snap: dict[str, Any] = {
            "ok": True,
            "state": self.state.value,
            "language": self.cfg.language or "auto",
            "autocorrect": "on" if self._autocorrect_active else "off",
        }
        if extra:
            snap.update(extra)
        return snap

    def _set_language(self, value: str | None) -> str:
        if value is None or value == "auto":
            self.cfg.language = None
        else:
            self.cfg.language = value
        display = self.cfg.language or "auto"
        output.notify("wayscribe", f"language: {display}")
        log.info("language set to %s", display)
        return display

    def _cycle_language(self) -> str:
        langs = self.cfg.languages or []
        if not langs:
            return self.cfg.language or "auto"
        current = self.cfg.language or "auto"
        try:
            idx = langs.index(current)
        except ValueError:
            idx = -1
        next_value = langs[(idx + 1) % len(langs)]
        return self._set_language(next_value)

    async def _sync_language_from_layout(self) -> None:
        if not self.cfg.language_from_layout:
            return
        lang = await keyboard.current_layout_lang()
        if lang and lang != self.cfg.language:
            self.cfg.language = lang
            log.info("language follows layout -> %s", lang)

    async def handle_command(self, msg: dict[str, Any]) -> dict[str, Any]:
        cmd = msg.get("cmd", "")
        if cmd == "status":
            # Probe outside the state lock: a slow/hung backend must not block
            # toggle/cancel/stop or the auto-stop watchdogs (all serialize on
            # self.lock) for the duration of the probe timeout.
            health = await probe_async(self.cfg)
            async with self.lock:
                return self._status_snapshot(
                    {
                        "endpoint": self.cfg.endpoint,
                        "backend": "up" if health.reachable else "down",
                    }
                )

        async with self.lock:
            if cmd == "stop":
                self.stop_event.set()
                return self._status_snapshot({"stopping": True})

            if cmd == "cancel":
                if self.state == State.RECORDING:
                    self._cancel_watchdogs()
                    await asyncio.to_thread(self.recorder.stop)
                    self.state = State.IDLE
                    await self._live_notify("wayscribe", "cancelled", icon="dialog-information")
                return self._status_snapshot()

            if cmd == "toggle":
                if self.state == State.IDLE:
                    return await self._start_recording_locked()
                if self.state == State.RECORDING:
                    return await self._stop_and_dispatch_locked(reason="toggle")
                output.notify("wayscribe", "still transcribing previous recording…")
                return self._status_snapshot({"ok": False, "reason": "busy"})

            if cmd == "lang_set":
                self._set_language(msg.get("value"))
                return self._status_snapshot()

            if cmd == "lang_next":
                self._cycle_language()
                return self._status_snapshot()

            if cmd == "fix":
                if self.state != State.IDLE:
                    return self._status_snapshot({"ok": False, "reason": "busy"})
                return await self._fix_locked(spell=msg.get("mode") == "spell")

            if cmd == "translate":
                if self.state != State.IDLE:
                    return self._status_snapshot({"ok": False, "reason": "busy"})
                return await self._translate_locked()

            if cmd == "autocorrect":
                if not self.cfg.evdev_autocorrect:
                    output.notify(
                        "wayscribe",
                        "autocorrect disabled (set evdev_autocorrect=true)",
                        icon="dialog-error",
                    )
                    return self._status_snapshot({"ok": False, "reason": "autocorrect-disabled"})
                return await self._set_autocorrect(msg.get("value") or "toggle")

            return {"ok": False, "error": f"unknown command: {cmd!r}"}

    @property
    def _autocorrect_active(self) -> bool:
        return self._autocorrect_task is not None and not self._autocorrect_task.done()

    async def _set_autocorrect(self, want: str) -> dict[str, Any]:
        """Start/stop the evdev grab. `want` is 'on' | 'off' | 'toggle'."""
        active = self._autocorrect_active
        target_on = not active if want == "toggle" else want == "on"
        if target_on and not active:
            from wayscribe.autocorrect import AutocorrectEngine

            engine = AutocorrectEngine(self.cfg)
            self._autocorrect_task = asyncio.create_task(engine.run())
            output.notify("wayscribe", "autocorrect ON", icon="media-record")
            log.info("autocorrect enabled")
        elif not target_on and active:
            await _drain_task(self._autocorrect_task)
            self._autocorrect_task = None
            output.notify("wayscribe", "autocorrect OFF", icon="dialog-information")
            log.info("autocorrect disabled")
        return self._status_snapshot()

    async def _grab_selection(self) -> str:
        """Capture the text to fix from the configured source (offloaded I/O)."""
        text = await asyncio.to_thread(
            selection.capture_target, self.cfg.fix_source, self.cfg.fix_last_word_count
        )
        return (text or "").strip()

    async def _write_back(self, text: str) -> bool:
        """Type the correction over the selection; notify + return False on failure."""
        try:
            await asyncio.to_thread(selection.replace_with, text)
            return True
        except Exception as exc:
            log.exception("write-back failed")
            output.notify("wayscribe", f"cannot type result: {exc}", icon="dialog-error")
            return False

    async def _fix_locked(self, spell: bool) -> dict[str, Any]:
        text = await self._grab_selection()
        if not text:
            output.notify("wayscribe", "no text selected", icon="dialog-information")
            return self._status_snapshot({"ok": False, "reason": "empty"})
        cand, conf, target = selection.propose_correction(text)
        if conf < self.cfg.trigram_confidence_min:
            # Not confident the text is wrong-layout. Defer to the LLM if it is
            # configured, otherwise leave the text alone (never write back the
            # gibberish re-keying of already-correct text).
            if llm.enabled(self.cfg):
                cand = await llm.fix_layout(text, self.cfg)
                target = None  # LLM may pick either language; skip the layout switch
            else:
                cand = text
        if spell and llm.enabled(self.cfg):
            cand = await llm.spellfix(cand, self.cfg)
        if cand == text:
            output.notify("wayscribe", "no change", icon="dialog-information")
            return self._status_snapshot({"ok": True, "changed": False})
        if not await self._write_back(cand):
            return self._status_snapshot({"ok": False, "reason": "write-failed"})
        if self.cfg.switch_layout and target:
            await keyboard.set_layout_by_lang(target)
        output.notify("wayscribe", f"{text} → {cand}", icon="dialog-information")
        log.info("fixed layout: %r -> %r (conf=%.2f)", text, cand, conf)
        return self._status_snapshot({"ok": True, "changed": True, "text": cand})

    async def _translate_locked(self) -> dict[str, Any]:
        if not llm.enabled(self.cfg):
            output.notify(
                "wayscribe", "LLM not configured (set llm_endpoint)", icon="dialog-error"
            )
            return self._status_snapshot({"ok": False, "reason": "llm-disabled"})
        text = await self._grab_selection()
        if not text:
            output.notify("wayscribe", "no text selected", icon="dialog-information")
            return self._status_snapshot({"ok": False, "reason": "empty"})
        out = (await llm.translate_to_en(text, self.cfg)).strip()
        if not out or out == text:
            output.notify("wayscribe", "no translation", icon="dialog-information")
            return self._status_snapshot({"ok": True, "changed": False})
        if not await self._write_back(out):
            return self._status_snapshot({"ok": False, "reason": "write-failed"})
        output.notify("wayscribe", f"{text} → {out}", icon="dialog-information")
        log.info("translated %d chars to en", len(text))
        return self._status_snapshot({"ok": True, "changed": True, "text": out})

    async def _start_recording_locked(self) -> dict[str, Any]:
        try:
            await asyncio.to_thread(self.recorder.start)
        except Exception as exc:
            log.exception("recorder failed to start")
            await self._live_notify(
                "wayscribe", f"mic error: {exc}", icon="dialog-error", new_cycle=True
            )
            return {"ok": False, "error": str(exc)}
        self.state = State.RECORDING
        await self._sync_language_from_layout()
        await self._live_notify(
            "wayscribe",
            "Recording… 0:00",
            icon="media-record",
            progress=0,
            timeout_ms=0,
            new_cycle=True,
        )
        self._max_duration_task = asyncio.create_task(self._max_duration_watchdog())
        if self.cfg.auto_stop:
            self._vad_task = asyncio.create_task(self._vad_watchdog())
        if self.cfg.live_notification and self._notify_supported:
            self._notify_task = asyncio.create_task(self._notify_updater())
        return self._status_snapshot()

    async def _stop_and_dispatch_locked(self, reason: str) -> dict[str, Any]:
        self._cancel_watchdogs()
        wav = await asyncio.to_thread(self.recorder.stop)
        self.state = State.TRANSCRIBING
        await self._live_notify("wayscribe", "Transcribing…", icon="view-refresh", timeout_ms=0)
        log.info("captured %d bytes (reason=%s)", len(wav), reason)
        self._inflight = asyncio.create_task(self._transcribe_and_output(wav))
        return self._status_snapshot({"bytes": len(wav), "reason": reason})

    def _cancel_watchdogs(self) -> None:
        current = asyncio.current_task()
        for attr in ("_max_duration_task", "_vad_task", "_notify_task"):
            task = getattr(self, attr)
            if task is not None and task is not current and not task.done():
                task.cancel()
            setattr(self, attr, None)

    async def _live_notify(
        self,
        title: str,
        body: str = "",
        *,
        icon: str = "audio-input-microphone",
        progress: int | None = None,
        timeout_ms: int | None = None,
        new_cycle: bool = False,
    ) -> None:
        """Emit/update the single live-feedback notification.

        Captures an id on the first frame of a cycle, then replaces it in place.
        notify-send runs in a thread (offload invariant). Falls back to a plain
        popup when disabled or when id capture is unsupported.
        """
        if not self.cfg.live_notification:
            await asyncio.to_thread(output.notify, title, body, icon)
            return
        if new_cycle:
            self._notify_id = None
            self._notify_supported = True
        if self._notify_supported and self._notify_id is None:
            nid = await asyncio.to_thread(
                output.notify_update,
                title,
                body,
                icon=icon,
                progress=progress,
                timeout_ms=timeout_ms,
                want_id=True,
            )
            if nid is None:
                self._notify_supported = False
            else:
                self._notify_id = nid
        elif self._notify_supported and self._notify_id is not None:
            await asyncio.to_thread(
                output.notify_update,
                title,
                body,
                icon=icon,
                replace_id=self._notify_id,
                progress=progress,
                timeout_ms=timeout_ms,
            )
        else:
            await asyncio.to_thread(output.notify, title, body, icon)

    async def _notify_updater(self) -> None:
        """While RECORDING, refresh the popup with elapsed time + mic-level bar.

        Reads state and the (thread-safe) recorder without the lock; a stale
        frame after a transition is benign and immediately overwritten.
        """
        try:
            while True:
                await asyncio.sleep(0.5)
                if self.state != State.RECORDING:
                    return
                elapsed = self.recorder.current_duration()
                level = vad.rms(self.recorder.peek_recent(0.3))
                pct = min(100, int(level / _LEVEL_FULL_SCALE * 100))
                await self._live_notify(
                    "wayscribe",
                    f"Recording… {_fmt_mmss(elapsed)}",
                    icon="media-record",
                    progress=pct,
                    timeout_ms=0,
                )
        except asyncio.CancelledError:
            return
        except Exception:
            # Never let a transient recorder/notify error kill the task
            # silently ("exception never retrieved"); the next cycle recovers.
            log.exception("notify updater failed")

    async def _max_duration_watchdog(self) -> None:
        try:
            await asyncio.sleep(self.cfg.max_duration_sec)
        except asyncio.CancelledError:
            return
        async with self.lock:
            if self.state != State.RECORDING:
                return
            log.info("max duration %.1fs reached, auto-stopping", self.cfg.max_duration_sec)
            output.notify("wayscribe", f"max duration reached ({int(self.cfg.max_duration_sec)}s)")
            await self._stop_and_dispatch_locked(reason="max-duration")

    async def _vad_watchdog(self) -> None:
        speech_seen = False
        silence_sec = self.cfg.auto_stop_silence_sec
        min_record = self.cfg.auto_stop_min_record_sec
        threshold = self.cfg.vad_rms_threshold
        try:
            while True:
                await asyncio.sleep(0.2)
                if self.state != State.RECORDING:
                    return
                duration = self.recorder.current_duration()
                if duration < min_record:
                    continue
                recent = self.recorder.peek_recent(0.5)
                if vad.has_speech(recent, threshold=threshold):
                    speech_seen = True
                    continue
                if not speech_seen:
                    continue
                window = self.recorder.peek_recent(silence_sec)
                if vad.has_speech(window, threshold=threshold):
                    continue
                async with self.lock:
                    if self.state != State.RECORDING:
                        return
                    log.info("VAD: %.1fs silence, auto-stopping", silence_sec)
                    await self._stop_and_dispatch_locked(reason="vad")
                return
        except asyncio.CancelledError:
            return

    def _effective_outputs(self) -> list[str]:
        outputs = list(self.cfg.outputs)
        if self.cfg.auto_type and "type" not in outputs:
            outputs.append("type")
        return outputs

    async def _transcribe_and_output(self, wav: bytes) -> None:
        try:
            text = await transcribe_async(wav, self.cfg)
        except httpx.ConnectError as exc:
            log.warning("FLM unreachable at %s: %s", self.cfg.endpoint, exc)
            await self._live_notify(
                "wayscribe", f"FLM unreachable ({self.cfg.endpoint})", icon="dialog-error"
            )
            self.state = State.IDLE
            return
        except Exception as exc:
            log.exception("transcription failed")
            await self._live_notify(
                "wayscribe", f"transcription failed: {exc}", icon="dialog-error"
            )
            self.state = State.IDLE
            return
        text = (text or "").strip()
        if not text:
            await self._live_notify("wayscribe", "(empty transcription)")
            self.state = State.IDLE
            return
        outputs = self._effective_outputs()
        for backend in outputs:
            if backend == "notify":
                continue  # delivered by the terminal frame below
            try:
                if backend == "clipboard":
                    output.to_clipboard(text)
                elif backend == "type":
                    output.type_text(text)
            except Exception:
                log.exception("output backend %r failed", backend)
        # Terminal frame: always fires when live_notification is on, so the
        # persistent "Transcribing…" frame is cleared even without a notify
        # backend. The transcript preview doubles as the notify output.
        preview = text if len(text) < 200 else text[:197] + "…"
        notify_requested = "notify" in outputs
        if self.cfg.live_notification:
            body = preview if notify_requested else f"done ({len(text)} chars)"
            await self._live_notify("wayscribe", body, icon="dialog-information")
        elif notify_requested:
            await self._live_notify("wayscribe", preview, icon="dialog-information")
        log.info("transcribed %d chars", len(text))
        self.state = State.IDLE

    async def warmup(self) -> None:
        if not self.cfg.warmup:
            return
        try:
            wav = silent_wav(1.0, sample_rate=self.cfg.sample_rate)
            await transcribe_async(wav, self.cfg)
            log.info("FLM warmup OK")
        except httpx.ConnectError:
            log.warning("FLM warmup skipped: %s not reachable", self.cfg.endpoint)
            output.notify(
                "wayscribe",
                f"backend unreachable at {self.cfg.endpoint} — run: wayscribe doctor",
                icon="dialog-error",
            )
        except Exception as exc:
            log.warning("FLM warmup failed: %s", exc)
            output.notify(
                "wayscribe", f"backend warmup failed: {exc}", icon="dialog-error"
            )


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
            if not isinstance(msg, dict):
                resp = {"ok": False, "error": "request must be a JSON object"}
            else:
                resp = await daemon.handle_command(msg)
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

    warmup_task = asyncio.create_task(daemon.warmup())

    try:
        async with server:
            await daemon.stop_event.wait()
    finally:
        daemon._cancel_watchdogs()
        await _drain_task(warmup_task)
        await _drain_task(daemon._autocorrect_task)
        await _drain_task(daemon._inflight)
        if daemon.recorder.is_recording:
            await asyncio.to_thread(daemon.recorder.stop)
        sock.unlink(missing_ok=True)
        log.info("daemon exited")


async def _drain_task(task: asyncio.Task[Any] | None) -> None:
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


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
