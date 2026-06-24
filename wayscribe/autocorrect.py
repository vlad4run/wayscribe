"""Phase-2 global autocorrect: watch the physical keyboard, fix wrong-layout
words as you type (Punto-Switcher style).

Security-sensitive (keylogger-class): gated behind `evdev_autocorrect` in config
and toggled at runtime by a hotkey (`wayscribe autocorrect`). The pure core
(`KEYCODE_CHARS`, `WordBuffer`) carries no evdev dependency so it is unit-tested
without a device; the live `AutocorrectEngine` imports `evdev` lazily.

The engine takes an exclusive grab (EVIOCGRAB) of each keyboard and replays
every event through a UInput device, so synthesized corrections (emitted via
ydotool, a *different* uinput device we do not watch) never feed back into our
buffer. Corrections reuse the Phase-1 output path (`output.backspace` +
`output.type_text`).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from wayscribe import keyboard, layout, output, selection
from wayscribe.config import Config

log = logging.getLogger("wayscribe")

# evdev key codes (== evdev.ecodes.KEY_*) -> (unshifted, shifted) US-QWERTY glyph.
# Mirrors the bijective set in layout.py; digits/space/etc. are handled separately.
KEYCODE_CHARS: dict[int, tuple[str, str]] = {
    16: ("q", "Q"), 17: ("w", "W"), 18: ("e", "E"), 19: ("r", "R"), 20: ("t", "T"),
    21: ("y", "Y"), 22: ("u", "U"), 23: ("i", "I"), 24: ("o", "O"), 25: ("p", "P"),
    26: ("[", "{"), 27: ("]", "}"),
    30: ("a", "A"), 31: ("s", "S"), 32: ("d", "D"), 33: ("f", "F"), 34: ("g", "G"),
    35: ("h", "H"), 36: ("j", "J"), 37: ("k", "K"), 38: ("l", "L"),
    39: (";", ":"), 40: ("'", '"'), 41: ("`", "~"),
    44: ("z", "Z"), 45: ("x", "X"), 46: ("c", "C"), 47: ("v", "V"), 48: ("b", "B"),
    49: ("n", "N"), 50: ("m", "M"), 51: (",", "<"), 52: (".", ">"), 53: ("/", "?"),
}

MOD_CODES: frozenset[int] = frozenset({42, 54})  # KEY_LEFTSHIFT, KEY_RIGHTSHIFT
SPACE = 57
BACKSPACE = 14
ENTER = 28
TAB = 15
# Punctuation that commits a word in place (safe to rewrite, like SPACE). Only
# key 53 ('/' '?' on US ↔ '.' ',' on RU) qualifies: it is the *only* physical key
# that is punctuation in both layouts, and it is the period/comma key for a
# Russian typist — so it cleanly signals "end of word" with zero risk of eating a
# Cyrillic letter. Every other US-punct key (',' '.' ';' "'" …) is a Cyrillic
# letter on the RU layout, so it must keep accumulating. Unlike SPACE, this glyph
# is itself part of the (possibly wrong-layout) text and gets re-keyed with the
# word: 'ghbdtn/' → 'привет.'.
PUNCT_TERMINATORS: frozenset[int] = frozenset({53})


@dataclass
class Correction:
    """A rewrite to apply: delete `backspaces` chars, then type `text`."""

    backspaces: int
    text: str
    target: str | None  # language of the corrected text ('ru'/'en') for layout switch
    original: str  # the on-screen wrong-layout word, for the notification preview


class WordBuffer:
    """Accumulates US-QWERTY glyphs from key presses; emits the raw word at a
    boundary.

    Pure and layout-agnostic: it records the *physical* keys (mapped to US
    glyphs), not what the active layout actually inserted. Reconstructing the
    on-screen text and deciding a correction is `decide`'s job, because that
    needs the active layout — which the buffer deliberately does not track.
    """

    def __init__(self) -> None:
        self._chars: list[str] = []

    def feed(self, code: int, shift: bool) -> str | None:
        """Feed one key press. Returns the completed raw word at a word boundary
        (SPACE / ENTER / TAB), else None."""
        if code in MOD_CODES:
            return None
        if code == BACKSPACE:
            if self._chars:
                self._chars.pop()
            return None
        if code in KEYCODE_CHARS:
            lo, hi = KEYCODE_CHARS[code]
            self._chars.append(hi if shift else lo)
            if code in PUNCT_TERMINATORS:
                # Commit the word *including* this punctuation glyph — it is part
                # of the wrong-layout run and gets re-keyed too (see decide).
                word = "".join(self._chars)
                self._chars = []
                return word
            return None
        if code == SPACE:
            word = "".join(self._chars)
            self._chars = []
            return word or None
        # ENTER / TAB / arrows / Home / End / Del / shortcuts: the word may be
        # done, but the cursor context is gone (Enter submits, Tab/arrows move
        # focus or caret), so the buffer no longer matches the screen — drop it,
        # take no action.
        self._chars = []
        return None


def decide(
    raw: str,
    active_lang: str | None,
    confidence_min: float,
    *,
    space_terminated: bool = True,
) -> Correction | None:
    """Decide whether the raw keystrokes were typed in the wrong layout.

    `raw` is the US-QWERTY reading of the physical keys; `active_lang` is the
    layout actually in effect, so the on-screen text is `raw` (Latin layout) or
    its Cyrillic re-key (Russian layout). We then run the Phase-1 plausibility
    check on that on-screen text and correct only when confident.

    `space_terminated` is True when a trailing SPACE was typed after the word
    (not part of `raw`): we delete one extra char and re-append the space. For a
    punctuation terminator the glyph is already inside `raw`/`onscreen`, so there
    is no extra char to delete or re-append.
    """
    onscreen = layout.en_to_ru(raw) if active_lang == "ru" else raw
    cand, conf, target = selection.propose_correction(onscreen)
    if cand == onscreen or conf < confidence_min:
        return None
    tail = " " if space_terminated else ""
    return Correction(
        backspaces=len(onscreen) + len(tail),
        text=cand + tail,
        target=target,
        original=onscreen,
    )


class AutocorrectEngine:
    """Live evdev grab+replay loop. Constructed only when the feature is on."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.buf = WordBuffer()
        self._shift = False

    def _fail(self, reason: str) -> None:
        log.warning("autocorrect: %s", reason)
        output.notify("wayscribe", f"autocorrect failed: {reason}", icon="dialog-error")

    def _find_keyboards(self, evdev):
        """Real keyboard devices, excluding our own/virtual injectors."""
        ecodes = evdev.ecodes
        found = []
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
            except OSError:
                continue
            caps = dev.capabilities()
            keys = caps.get(ecodes.EV_KEY, [])
            name = (dev.name or "").lower()
            if ecodes.KEY_A in keys and not any(
                tag in name for tag in ("ydotool", "uinput", "wayscribe")
            ):
                found.append(dev)
            else:
                dev.close()
        return found

    async def run(self) -> None:
        try:
            import evdev
        except ImportError:
            self._fail("python-evdev not installed")
            return

        try:
            devices = self._find_keyboards(evdev)
        except PermissionError:
            self._fail("no /dev/input access (add user to 'input' group)")
            return
        if not devices:
            # list_devices() only returns readable nodes, so a permission
            # problem looks identical to "no keyboard" here. Disambiguate by
            # checking whether event nodes exist but are unreadable.
            import glob
            import os

            nodes = glob.glob("/dev/input/event*")
            if nodes and not any(os.access(n, os.R_OK) for n in nodes):
                self._fail("no /dev/input access (add user to 'input' group)")
            else:
                self._fail("no keyboard found")
            return

        ui = None
        grabbed: list = []
        try:
            ui = evdev.UInput.from_device(*devices, name="wayscribe-autocorrect")
            for dev in devices:
                dev.grab()
                grabbed.append(dev)
            log.info("autocorrect: grabbed %d keyboard(s)", len(grabbed))
            await asyncio.gather(*(self._pump(dev, ui, evdev) for dev in grabbed))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("autocorrect engine crashed")
            output.notify("wayscribe", "autocorrect stopped (error)", icon="dialog-error")
        finally:
            for dev in grabbed:
                try:
                    dev.ungrab()
                except Exception:
                    pass
                dev.close()
            if ui is not None:
                ui.close()
            log.info("autocorrect: released keyboards")

    async def _pump(self, dev, ui, evdev) -> None:
        ecodes = evdev.ecodes
        async for ev in dev.async_read_loop():
            # Replay the original event (the grab swallowed it from the app).
            ui.write_event(ev)
            ui.syn()
            if ev.type != ecodes.EV_KEY:
                continue
            if ev.code in MOD_CODES:
                self._shift = ev.value != 0  # press/repeat = held, release = up
                continue
            if ev.value != 1:  # act on key-press only (skip release/repeat)
                continue
            word = self.buf.feed(ev.code, self._shift)
            if word is not None:
                await self._handle_word(word, space_terminated=ev.code == SPACE)

    async def _handle_word(self, raw: str, *, space_terminated: bool) -> None:
        active = await keyboard.current_layout_lang()
        correction = decide(
            raw, active, self.cfg.trigram_confidence_min, space_terminated=space_terminated
        )
        if correction is not None:
            await self._apply(correction)

    async def _apply(self, c: Correction) -> None:
        try:
            await asyncio.to_thread(output.backspace, c.backspaces)
            await asyncio.to_thread(output.type_text, c.text)
        except Exception:
            log.exception("autocorrect: failed to apply correction")
            return
        # Live autocorrect always flips the layout to the corrected text's
        # language (Punto-Switcher style): without it the next word is typed in
        # the same wrong layout and re-triggers a fix every time. The
        # `switch_layout` config flag governs only the explicit `fix` command.
        if c.target:
            await keyboard.set_layout_by_lang(c.target)
        # NB: never log c.original / the corrected text — this engine sees every
        # keystroke, so journaling typed words would leak passwords and private
        # content into a persistent, admin-readable log. The transient notify is
        # the only surface allowed to show the word.
        fixed = c.text.rstrip(" ")
        await asyncio.to_thread(
            output.notify, "wayscribe", f"{c.original} → {fixed}", "dialog-information"
        )
