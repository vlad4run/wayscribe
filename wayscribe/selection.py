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


# Confidence returned for a word-gate match: "certain", clears any finite
# trigram_confidence_min threshold. The n-gram tier returns a log-prob delta.
_GATE_CONFIDENCE = float("inf")


def propose_correction(text: str) -> tuple[str, float, str | None]:
    """Re-key `text` into the other layout; return (candidate, confidence, target).

    Two-tier cascade — the caller thresholds `confidence` on
    `trigram_confidence_min`, then defers to the LLM:

    * word-gate: the candidate is a real word in the target language and the
      original is *not* a real word in the source language (and the n-gram agrees
      it reads at least as well). A near-certain layout mistake → confidence is
      `inf`.
    * n-gram: otherwise the mean trigram log-probability delta
      `logp(candidate, target) - logp(original, source)` — a graceful,
      vocabulary-independent fallback (positive = candidate reads better).

    `target` is the language the candidate is in ('ru'/'en'), for the optional
    KDE layout switch. Returns `(text, 0.0, None)` for non-Latin/Cyrillic input.
    """
    sc = _script(text)
    if sc == "en":  # Latin glyphs that may be Russian typed on the wrong layout.
        cand, target, src = layout.en_to_ru(text), "ru", "en"
    elif sc == "ru":  # Cyrillic glyphs that may be English typed on the wrong layout.
        cand, target, src = layout.ru_to_en(text), "en", "ru"
    else:
        return text, 0.0, None
    delta = langdetect.logp(cand, target) - langdetect.logp(text, src)
    if delta >= 0 and langdetect.word_known(cand, target) and not langdetect.word_known(text, src):
        return cand, _GATE_CONFIDENCE, target
    return cand, delta, target


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
