"""Trigram scoring: real words score for their language, junk scores low."""
from __future__ import annotations

from wayscribe import langdetect


def test_russian_word_scores_ru() -> None:
    s = langdetect.score("привет")
    assert s["ru"] > s["en"]


def test_english_word_scores_en() -> None:
    s = langdetect.score("hello")
    assert s["en"] > s["ru"]


def test_wrong_layout_junk_scores_low_in_both() -> None:
    # ghbdtn (привет on the wrong layout) reads as junk until re-keyed.
    s = langdetect.score("ghbdtn")
    assert s["ru"] == 0.0 and s["en"] == 0.0


def test_short_and_empty_do_not_crash() -> None:
    assert langdetect.score("") == {"ru": 0.0, "en": 0.0}
    # Space-padding gives 1-2 char strings real trigrams; result stays well-formed.
    s = langdetect.score("ab")
    assert set(s) == {"ru", "en"} and all(0.0 <= v <= 1.0 for v in s.values())
