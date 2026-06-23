"""Trigram-based language plausibility scoring for layout-mismatch detection.

Decides whether a string reads as Russian or English by what fraction of its
character trigrams appear in a curated set of that language's common trigrams.
The tables are embedded `.py` constants (no corpus file, no package-data) — they
need not be exhaustive: the layout fixer only compares two candidate spellings
and picks the more plausible one, so relative coverage is what matters.

`score("привет") -> {"ru": 1.0, "en": 0.0}`. Callers compare the score of two
candidate spellings (the text as typed vs. its layout re-key) to pick a winner.
"""
from __future__ import annotations

# Common Russian trigrams (lowercase). Curated, not exhaustive.
_RU_TRIGRAMS: frozenset[str] = frozenset(
    """
    сто ост ова ого ени ние тор при про ско тся ест тел ани его что как это
    для был она они вет рив иве ств тве енн нно ому льн ель ная ный ыми ват
    ить ало али ала ает ают аем нии тра тре сти сте ска нос нов раз рас рос
    пер пре под над пол кол кот мог мож дел ден дни вре
    """.split()
)

# Common English trigrams (lowercase). Curated, not exhaustive.
_EN_TRIGRAMS: frozenset[str] = frozenset(
    """
    the and ing her hat his tha ere ent ion ter was you ith ver all wit thi
    tio nde has men ted ers are not but had hen one our day out who any see
    way com pro con res per ble ack ear est ave ght ome oul hin tin ell llo
    hel orl wor rld near rea con int sta ist ica eve ect ess ive nce ons
    """.split()
)


def _trigrams(text: str) -> list[str]:
    """Lowercase trigrams over the raw string (spaces/punctuation included).

    Padding-free: short strings (<3 chars) yield none, which scores 0 and lets
    the caller treat them as undecidable rather than crashing.
    """
    s = text.lower()
    return [s[i : i + 3] for i in range(len(s) - 2)]


def _coverage(grams: list[str], table: frozenset[str]) -> float:
    if not grams:
        return 0.0
    return sum(1 for g in grams if g in table) / len(grams)


def score(text: str) -> dict[str, float]:
    """Fraction of `text`'s trigrams found in each language's common set."""
    grams = _trigrams(text)
    return {"ru": _coverage(grams, _RU_TRIGRAMS), "en": _coverage(grams, _EN_TRIGRAMS)}
