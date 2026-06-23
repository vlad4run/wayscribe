"""Output backends: clipboard (wl-copy), keystroke synthesis (wtype/ydotool), KDE notify.

Missing tools surface as `RuntimeError` for primary backends (clipboard, type)
so the daemon can log them. `notify` is best-effort and silently no-ops if
`notify-send` isn't installed.
"""
from __future__ import annotations

import os
import shutil
import subprocess


def to_clipboard(text: str) -> None:
    try:
        subprocess.run(["wl-copy"], input=text.encode(), check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("wl-copy not found (install wl-clipboard)") from exc


def type_text(text: str) -> None:
    have_wtype = shutil.which("wtype") is not None
    have_ydotool = shutil.which("ydotool") is not None
    if not have_wtype and not have_ydotool:
        raise RuntimeError(
            "no keystroke tool found — install ydotool (KWin/Plasma) or wtype (wlroots)"
        )
    # wtype needs zwp_virtual_keyboard_manager_v1, which KWin (Plasma) does not
    # implement, so wtype always fails on KDE. When ydotool is present there,
    # use it first and skip the guaranteed-failing wtype spawn.
    is_kde = "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "")
    prefer_ydotool = is_kde and have_ydotool
    if have_wtype and not prefer_ydotool:
        try:
            subprocess.run(["wtype", "--", text], check=True)
            return
        except subprocess.CalledProcessError:
            # Fall back to ydotool (e.g. KWin with XDG_CURRENT_DESKTOP unset).
            if not have_ydotool:
                raise RuntimeError(
                    "wtype failed — on KWin/Plasma install ydotool "
                    "(wtype works only on wlroots compositors)"
                ) from None
    # Reached when ydotool is the chosen path (preferred, or wtype absent/failed).
    # ydotool `type` maps ASCII -> evdev keycodes only; non-ASCII characters have
    # no mapping and are silently dropped (Cyrillic transcripts come out as just
    # the surviving ASCII punctuation). For any non-ASCII text, paste via the
    # clipboard instead, which is layout/charset agnostic.
    if text.isascii():
        subprocess.run(["ydotool", "type", "--", text], check=True)
    else:
        _ydotool_paste(text)


# Raw evdev keycodes used for synthesized chords (ydotool `key` takes CODE:STATE).
_KEY_LEFTCTRL = 29
_KEY_LEFTSHIFT = 42
_KEY_BACKSPACE = 14
_KEY_LEFT = 105
_KEY_V = 47
_KEY_INSERT = 110

# Shift+Insert (paste): press shift, tap insert, release shift.
# Universal paste chord — works in terminals (Konsole, whose Paste is Ctrl+Shift+V,
# not Ctrl+V) *and* Qt/GTK text entries, unlike Ctrl+V which terminals ignore.
_PASTE_KEYS = [f"{_KEY_LEFTSHIFT}:1", f"{_KEY_INSERT}:1", f"{_KEY_INSERT}:0", f"{_KEY_LEFTSHIFT}:0"]


def _require_ydotool() -> None:
    if shutil.which("ydotool") is None:
        raise RuntimeError("ydotool not found — required for keystroke synthesis")


def backspace(count: int) -> None:
    """Synthesize `count` Backspace presses via ydotool (deletes typed-but-wrong text)."""
    if count <= 0:
        return
    _require_ydotool()
    keys = [f"{_KEY_BACKSPACE}:1", f"{_KEY_BACKSPACE}:0"] * count
    subprocess.run(["ydotool", "key", *keys], check=True)


def select_words_left(count: int) -> None:
    """Select `count` words to the left (Ctrl+Shift+Left × count) via ydotool.

    Used to grab the just-typed word(s) into the selection when no explicit
    selection exists. Tap Left while Ctrl+Shift are held, then release both.
    """
    if count <= 0:
        return
    _require_ydotool()
    keys = [f"{_KEY_LEFTCTRL}:1", f"{_KEY_LEFTSHIFT}:1"]
    keys += [f"{_KEY_LEFT}:1", f"{_KEY_LEFT}:0"] * count
    keys += [f"{_KEY_LEFTSHIFT}:0", f"{_KEY_LEFTCTRL}:0"]
    subprocess.run(["ydotool", "key", *keys], check=True)


def _ydotool_paste(text: str) -> None:
    """Put `text` on the clipboard and synthesize Shift+Insert via ydotool.

    Used for non-ASCII transcripts that ydotool `type` cannot emit. Overwrites
    the clipboard (unavoidable for a paste); the `type` backend is already a
    keystroke-synthesis path, so this stays within that contract.
    """
    to_clipboard(text)
    subprocess.run(["ydotool", "key", *_PASTE_KEYS], check=True)


def _send_notification(
    title: str,
    body: str = "",
    *,
    icon: str = "audio-input-microphone",
    replace_id: int | None = None,
    progress: int | None = None,
    timeout_ms: int | None = None,
    capture_id: bool = False,
) -> int | None:
    """Fire a `notify-send`. Returns the notification id when `capture_id`.

    `replace_id` updates a notification in place; `progress` (0-100) renders a
    progress bar on KDE via the `value` hint; `timeout_ms=0` means persistent.
    Best-effort: a missing `notify-send` is a silent no-op (returns None).
    """
    argv = ["notify-send", "--app-name=wayscribe", "--icon", icon]
    if replace_id is not None:
        argv += ["--replace-id", str(replace_id)]
    if progress is not None:
        argv += ["--hint", f"int:value:{progress}"]
    if timeout_ms is not None:
        argv += ["--expire-time", str(timeout_ms)]
    if capture_id:
        argv.append("--print-id")
    argv += [title, body]
    try:
        if capture_id:
            proc = subprocess.run(argv, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                return None
            try:
                return int(proc.stdout.strip())
            except ValueError:
                return None
        subprocess.run(argv, check=False)
    except FileNotFoundError:
        pass
    return None


def notify(title: str, body: str = "", icon: str = "audio-input-microphone") -> None:
    _send_notification(title, body, icon=icon)


def notify_update(
    title: str,
    body: str = "",
    *,
    icon: str = "audio-input-microphone",
    replace_id: int | None = None,
    progress: int | None = None,
    timeout_ms: int | None = None,
    want_id: bool = False,
) -> int | None:
    """Live-feedback notification: capture/replace an id, set a progress bar."""
    return _send_notification(
        title,
        body,
        icon=icon,
        replace_id=replace_id,
        progress=progress,
        timeout_ms=timeout_ms,
        capture_id=want_id,
    )
