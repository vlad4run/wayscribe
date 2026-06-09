"""Query the active KDE keyboard layout to pick a transcription language.

Talks to KWin's `org.kde.KeyboardLayouts` D-Bus interface via `gdbus` (glib2,
always present on KDE — keeps zero pip deps and survives the PyInstaller
bundle). Everything here is best-effort: any failure (non-KDE session, no
session bus, gdbus missing, unparseable output) returns ``None`` so the caller
falls back to the configured language.
"""
from __future__ import annotations

import asyncio
import logging
import re

log = logging.getLogger("flm-voice")

_DEST = "org.kde.KWin"
_PATH = "/Layouts"
_IFACE = "org.kde.KeyboardLayouts"

# xkb layout codes that don't match ISO-639-1. Codes that already coincide
# (ru, de, fr, es, it, …) pass through unchanged.
_XKB_TO_ISO = {"us": "en", "gb": "en"}

_INT_RE = re.compile(r"uint32\s+(\d+)")
_CODE_RE = re.compile(r"\('([^']*)'")


async def _gdbus(method: str, timeout: float = 2.0) -> str | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "gdbus", "call", "--session",
            "--dest", _DEST,
            "--object-path", _PATH,
            "--method", f"{_IFACE}.{method}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return None
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        return None
    if proc.returncode != 0:
        return None
    return out.decode(errors="replace")


def _xkb_to_iso(code: str) -> str | None:
    code = code.lower()
    if code in _XKB_TO_ISO:
        return _XKB_TO_ISO[code]
    if len(code) == 2 and code.isalpha():
        return code
    return None


async def current_layout_lang() -> str | None:
    """ISO-639-1 hint for the active KDE layout, or None if undeterminable."""
    idx_out = await _gdbus("getLayout")
    list_out = await _gdbus("getLayoutsList")
    if idx_out is None or list_out is None:
        return None
    m = _INT_RE.search(idx_out)
    if not m:
        return None
    idx = int(m.group(1))
    codes = _CODE_RE.findall(list_out)
    if idx >= len(codes):
        return None
    lang = _xkb_to_iso(codes[idx])
    log.debug("layout idx=%d code=%r -> lang=%r", idx, codes[idx], lang)
    return lang
