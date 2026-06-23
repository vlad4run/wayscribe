"""Capture the text to fix, decide the correction, and write it back.

Phase-1 (no global keylogger): the text comes from the Wayland PRIMARY
selection (`wl-paste --primary`) — either an explicit user highlight, or the
just-typed word(s) grabbed by synthesizing Ctrl+Shift+Left first. The pure
`propose_correction` (layout re-key + trigram plausibility) is split from the
subprocess I/O so it can be unit-tested without a compositor.
"""
from __future__ import annotations

import logging
import subprocess
import time

from wayscribe import langdetect, layout, output

log = logging.getLogger("wayscribe")


def _script(text: str) -> str | None:
    """Dominant alphabet of `text`: 'en' (Latin), 'ru' (Cyrillic), or None."""
    latin = sum(1 for ch in text if "a" <= ch.lower() <= "z")
    cyr = sum(1 for ch in text if "а" <= ch.lower() <= "я" or ch.lower() == "ё")
    if latin == cyr == 0:
        return None
    return "en" if latin >= cyr else "ru"


def propose_correction(text: str) -> tuple[str, float, str | None]:
    """Re-key `text` into the other layout; return (candidate, confidence, target).

    Confidence in [-1, 1] is how much more plausible the re-keyed candidate is
    than the text as typed (trigram coverage of the target language minus that
    of the source). Negative/low means the text was probably fine as-is; the
    caller thresholds on it (and may defer to the LLM). `target` is the language
    the candidate is in ('ru'/'en'), used for the optional KDE layout switch.
    """
    sc = _script(text)
    if sc == "en":  # Latin glyphs that may be Russian typed on the wrong layout.
        cand = layout.en_to_ru(text)
        conf = langdetect.score(cand)["ru"] - langdetect.score(text)["en"]
        return cand, conf, "ru"
    if sc == "ru":  # Cyrillic glyphs that may be English typed on the wrong layout.
        cand = layout.ru_to_en(text)
        conf = langdetect.score(cand)["en"] - langdetect.score(text)["ru"]
        return cand, conf, "en"
    return text, 0.0, None


def read_primary() -> str:
    """Current PRIMARY selection, or '' if empty/unavailable (best-effort)."""
    try:
        proc = subprocess.run(
            ["wl-paste", "--primary", "--no-newline"],
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("wl-paste not found (install wl-clipboard)") from exc
    if proc.returncode != 0:
        return ""
    return proc.stdout.decode(errors="replace")


def capture_target(source: str, last_word_count: int) -> str:
    """Grab the text to fix: an explicit selection, or the just-typed word(s)."""
    if source == "last_word":
        output.select_words_left(last_word_count)
        time.sleep(0.05)  # let the synthesized selection propagate to PRIMARY
    return read_primary()


def replace_with(text: str) -> None:
    """Overwrite the active selection by typing the corrected text over it."""
    output.type_text(text)
