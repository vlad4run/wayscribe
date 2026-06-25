"""langdetect: word-gate membership + trigram log-probability scoring."""

from __future__ import annotations

from wayscribe import _langdata, langdetect


def test_word_known_real_words() -> None:
    assert langdetect.word_known("привет", "ru")
    assert langdetect.word_known("hello", "en")


def test_word_known_rejects_wrong_layout_junk() -> None:
    # ghbdtn (привет mis-keyed) is not an English word; nor a Russian one.
    assert not langdetect.word_known("ghbdtn", "en")
    assert not langdetect.word_known("ghbdtn", "ru")


def test_word_known_strips_edge_punctuation_and_case() -> None:
    assert langdetect.word_known("Привет.", "ru")  # case + trailing dot
    assert langdetect.word_known("hello!", "en")
    assert not langdetect.word_known("ghbdtn/", "en")  # still not a word


def test_logp_prefers_native_language() -> None:
    assert langdetect.logp("привет", "ru") > langdetect.logp("привет", "en")
    assert langdetect.logp("hello", "en") > langdetect.logp("hello", "ru")


def test_logp_empty_returns_floor() -> None:
    assert langdetect.logp("", "ru") == _langdata.RU_LOGP_FLOOR
    assert langdetect.logp("", "en") == _langdata.EN_LOGP_FLOOR


def test_logp_finite_and_nonpositive_on_short_input() -> None:
    v = langdetect.logp("ab", "en")
    assert isinstance(v, float) and v <= 0.0
