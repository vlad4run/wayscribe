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
    subprocess.run(["ydotool", "type", "--", text], check=True)


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
