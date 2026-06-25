"""Language plausibility for layout-mismatch detection.

Two signals over the generated tables in `_langdata` (that module is DATA ONLY,
rewritten by `scripts/gen_langdata.py` — do not hand-edit it):

* `word_known(text, lang)` — exact membership in the language's known-word set.
  The high-precision gate: a wrong-layout string ("ghbdtn") is almost never a
  real word, while its re-key ("привет") is — so a real candidate whose original
  is *not* a real word is a near-certain layout mistake.
* `logp(text, lang)` — mean add-k-smoothed log-probability of the text's
  space-padded character trigrams; the graceful fallback for out-of-vocabulary
  tokens (names, slang, code, inflections missing from the wordlist). Callers
  compare `logp(candidate, target) - logp(original, source)`: positive means the
  re-keyed candidate reads better in the target language than the text as typed.

Both are pure and dependency-free; the heavy data lives in `_langdata`.
"""

from __future__ import annotations

from wayscribe import _langdata as _d

_WORDS = {"ru": _d.RU_WORDS, "en": _d.EN_WORDS}
_LOGP = {"ru": _d.RU_TRIGRAM_LOGP, "en": _d.EN_TRIGRAM_LOGP}
_FLOOR = {"ru": _d.RU_LOGP_FLOOR, "en": _d.EN_LOGP_FLOOR}

# Surrounding punctuation/whitespace stripped before a word-set lookup, so a
# punctuation-terminated token ("привет." / "ghbdtn/") matches its bare word.
_EDGE = " \t\n.,;:!?/\\'\"()[]{}<>«»—–-…"


def word_known(text: str, lang: str) -> bool:
    """True if `text` (lowercased, edge punctuation stripped) is a known `lang` word."""
    return text.lower().strip(_EDGE) in _WORDS[lang]


def _padded_trigrams(text: str) -> list[str]:
    s = f" {text.lower()} "
    return [s[i : i + 3] for i in range(len(s) - 2)]


def logp(text: str, lang: str) -> float:
    """Mean log-probability of `text`'s space-padded trigrams under `lang`.

    Length-normalized (mean, not sum) so one threshold works across word lengths;
    trigrams absent from the table get the language's floor log-prob. The empty
    string (padding only) yields no trigrams and returns the floor.
    """
    grams = _padded_trigrams(text)
    if not grams:
        return _FLOOR[lang]
    table, floor = _LOGP[lang], _FLOOR[lang]
    return sum(table.get(g, floor) for g in grams) / len(grams)
