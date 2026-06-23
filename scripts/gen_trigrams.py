#!/usr/bin/env python3
"""Regenerate the embedded trigram tables in wayscribe/langdetect.py.

Reads hunspell wordlists (word-per-line, `word/FLAGS`), counts boundary-padded
character trigrams across the vocabulary, and rewrites `wayscribe/langdetect.py`
with the top-N per language baked in as frozenset literals. The runtime keeps no
corpus dependency: the tables are embedded `.py` constants. Re-run only when
retuning detection, then `ruff format` the result.

    python scripts/gen_trigrams.py [N]   # default N=900; rewrites the module
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

RU_DIC = Path("/usr/share/hunspell/ru_RU.dic")
EN_DIC = Path("/usr/share/hunspell/en_US.dic")
MODULE = Path(__file__).resolve().parent.parent / "wayscribe" / "langdetect.py"

_TEMPLATE = '''\
"""Trigram-based language plausibility scoring for layout-mismatch detection.

Decides whether a string reads as Russian or English by what fraction of its
character trigrams appear in a frequency-ranked set of that language's common
trigrams. The tables are embedded `.py` constants (no corpus file, no
package-data); they are regenerated from hunspell wordlists by
`scripts/gen_trigrams.py` (top {n} boundary-padded trigrams per language). The
layout fixer only compares two candidate spellings and picks the more plausible
one, so relative coverage is what matters.

Trigrams are counted over the word *padded with spaces* (`" word "`), so the
first/last trigram of every word — and short function words — get represented;
`_trigrams` pads identically at score time. `score("привет") -> {{"ru": ...,
"en": 0.0}}`. Callers compare the score of two candidate spellings (the text as
typed vs. its layout re-key) to pick a winner.
"""
from __future__ import annotations

# Top {n} space-padded Russian trigrams by vocabulary frequency (hunspell ru_RU).
_RU_TRIGRAMS: frozenset[str] = frozenset(
    [
{ru}
    ]
)

# Top {n} space-padded English trigrams by vocabulary frequency (hunspell en_US).
_EN_TRIGRAMS: frozenset[str] = frozenset(
    [
{en}
    ]
)


def _trigrams(text: str) -> list[str]:
    """Lowercase, space-padded trigrams over the string.

    Padding (`" text "`) mirrors how the tables were built, so a word's edge
    trigrams count and short words (1-2 chars) still yield trigrams instead of
    scoring 0. The empty string pads to two spaces and yields none.
    """
    s = f" {{text.lower()}} "
    return [s[i : i + 3] for i in range(len(s) - 2)]


def _coverage(grams: list[str], table: frozenset[str]) -> float:
    if not grams:
        return 0.0
    return sum(1 for g in grams if g in table) / len(grams)


def score(text: str) -> dict[str, float]:
    """Fraction of `text`'s trigrams found in each language's common set."""
    grams = _trigrams(text)
    return {{"ru": _coverage(grams, _RU_TRIGRAMS), "en": _coverage(grams, _EN_TRIGRAMS)}}
'''


def _is_alpha(word: str, lo: str, hi: str) -> bool:
    return bool(word) and all(lo <= ch <= hi or ch == "ё" for ch in word)


def _words(dic: Path, lo: str, hi: str) -> list[str]:
    out = []
    for line in dic.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        word = line.split("/", 1)[0].strip().lower()
        if _is_alpha(word, lo, hi):
            out.append(word)
    return out


def _top_trigrams(words: list[str], n: int) -> list[str]:
    counts: Counter[str] = Counter()
    for w in words:
        s = f" {w} "  # boundary padding: capture word-edge trigrams too
        for i in range(len(s) - 2):
            counts[s[i : i + 3]] += 1
    return sorted(g for g, _ in counts.most_common(n))


def _fmt(grams: list[str], per_line: int = 8) -> str:
    rows = []
    for i in range(0, len(grams), per_line):
        rows.append("        " + ", ".join(repr(g) for g in grams[i : i + per_line]) + ",")
    return "\n".join(rows)


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 900
    ru = _top_trigrams(_words(RU_DIC, "а", "я"), n)  # noqa: RUF001 (Cyrillic range bounds)
    en = _top_trigrams(_words(EN_DIC, "a", "z"), n)
    MODULE.write_text(_TEMPLATE.format(n=n, ru=_fmt(ru), en=_fmt(en)), encoding="utf-8")
    print(f"wrote {MODULE} (ru={len(ru)} en={len(en)} trigrams)")


if __name__ == "__main__":
    main()
