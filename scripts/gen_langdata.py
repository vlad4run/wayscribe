#!/usr/bin/env python3
"""Regenerate the embedded language tables in wayscribe/_langdata.py.

Reads hunspell wordlists (word-per-line, `word/FLAGS`) and bakes two things per
language into `wayscribe/_langdata.py` as plain `.py` constants — so the runtime
keeps **no corpus dependency** and the PyInstaller binary is unchanged:

  * ``*_WORDS``        — frozenset of known lowercase words, for the precision
                         word-gate (`langdetect.word_known`).
  * ``*_TRIGRAM_LOGP`` — dict of space-padded char trigram -> add-k smoothed
                         log-probability, with ``*_LOGP_FLOOR`` for unseen
                         trigrams, for the n-gram tier (`langdetect.logp`).

Only `_langdata.py` is rewritten; the scoring logic lives in the hand-written
`wayscribe/langdetect.py` and is never touched here. Re-run when retuning
detection or adding a language, then `ruff format` the result.

    python scripts/gen_langdata.py        # rewrites wayscribe/_langdata.py
"""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "wayscribe" / "_langdata.py"

# (lang, dic path, alphabet bounds). Add a row to support another language;
# the per-pair *layout* map still lives in wayscribe/layout.py.
LANGS = [
    ("ru", Path("/usr/share/hunspell/ru_RU.dic"), "а", "я"),  # noqa: RUF001
    ("en", Path("/usr/share/hunspell/en_US.dic"), "a", "z"),
]

ADD_K = 0.5  # add-k (Lidstone) smoothing for trigram probabilities


def _is_alpha(word: str, lo: str, hi: str) -> bool:
    return bool(word) and all(lo <= ch <= hi or ch == "ё" for ch in word)


def _words(dic: Path, lo: str, hi: str) -> list[str]:
    out: set[str] = set()
    for line in dic.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        word = line.split("/", 1)[0].strip().lower()
        if _is_alpha(word, lo, hi):
            out.add(word)
    return sorted(out)


def _trigram_logp(words: list[str]) -> tuple[dict[str, float], float]:
    """Add-k smoothed log-probabilities of space-padded trigrams over the vocab.

    Type frequency (counted once per distinct word), matching the original
    table's construction. Returns (logp_by_trigram, floor_for_unseen)."""
    counts: Counter[str] = Counter()
    for w in words:
        s = f" {w} "  # boundary padding so word-edge trigrams are represented
        for i in range(len(s) - 2):
            counts[s[i : i + 3]] += 1
    total = sum(counts.values())
    v = len(counts)
    denom = total + ADD_K * (v + 1)
    logp = {g: round(math.log((c + ADD_K) / denom), 4) for g, c in counts.items()}
    floor = round(math.log(ADD_K / denom), 4)
    return dict(sorted(logp.items())), floor


def _fmt_words(words: list[str], per_line: int = 10) -> str:
    rows = []
    for i in range(0, len(words), per_line):
        rows.append("        " + ", ".join(repr(w) for w in words[i : i + per_line]) + ",")
    return "\n".join(rows)


def _fmt_logp(logp: dict[str, float], per_line: int = 4) -> str:
    items = list(logp.items())
    rows = []
    for i in range(0, len(items), per_line):
        chunk = items[i : i + per_line]
        rows.append("        " + ", ".join(f"{g!r}: {p}" for g, p in chunk) + ",")
    return "\n".join(rows)


_HEADER = '''\
"""Generated language tables for layout-mismatch detection. DO NOT EDIT.

Rewritten by ``scripts/gen_langdata.py`` from hunspell wordlists. Data only — the
scoring logic lives in ``wayscribe/langdetect.py``. Per language:

  ``*_WORDS``        known lowercase words (precision word-gate)
  ``*_TRIGRAM_LOGP`` space-padded trigram -> add-k smoothed log P(trigram)
  ``*_LOGP_FLOOR``   log-prob assigned to trigrams absent from the table
"""
from __future__ import annotations

'''


def main() -> None:
    parts = [_HEADER]
    for lang, dic, lo, hi in LANGS:
        words = _words(dic, lo, hi)
        logp, floor = _trigram_logp(words)
        up = lang.upper()
        parts.append(
            f"# {len(words)} known {lang} words (hunspell {dic.name}).\n"
            f"{up}_WORDS: frozenset[str] = frozenset(\n    [\n{_fmt_words(words)}\n    ]\n)\n"
        )
        parts.append(
            f"# {len(logp)} space-padded {lang} trigram log-probabilities.\n"
            f"{up}_TRIGRAM_LOGP: dict[str, float] = {{\n{_fmt_logp(logp)}\n}}\n"
            f"{up}_LOGP_FLOOR: float = {floor}\n"
        )
    MODULE.write_text("\n".join(parts), encoding="utf-8")
    sizes = ", ".join(f"{lang}={len(_words(d, lo, hi))}w" for lang, d, lo, hi in LANGS)
    print(f"wrote {MODULE} ({sizes}); now run: .venv/bin/ruff format {MODULE}")


if __name__ == "__main__":
    main()
