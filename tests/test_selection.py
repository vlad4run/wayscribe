"""propose_correction: direction, confidence, pass-through (pure, no I/O)."""

from __future__ import annotations

import math

from wayscribe import langdetect, selection


def test_latin_typed_russian_is_corrected() -> None:
    cand, conf, target = selection.propose_correction("ghbdtn")
    assert cand == "привет"
    assert target == "ru"
    assert conf > 0


def test_cyrillic_typed_english_is_corrected() -> None:
    cand, conf, target = selection.propose_correction("руддщ")
    assert cand == "hello"
    assert target == "en"
    assert conf > 0


def test_correct_english_has_low_confidence() -> None:
    # Already-correct text re-keys to junk, so confidence must be non-positive
    # — the daemon uses that to leave it alone.
    _, conf, _ = selection.propose_correction("hello")
    assert conf <= 0


def test_correct_russian_has_low_confidence() -> None:
    _, conf, _ = selection.propose_correction("привет")
    assert conf <= 0


def test_no_letters_is_noop() -> None:
    cand, conf, target = selection.propose_correction("12 34")
    assert cand == "12 34"
    assert conf == 0.0
    assert target is None


def test_word_gate_match_is_certain() -> None:
    # Real target word + non-word original -> tier-1 word-gate -> certain (inf),
    # so it clears any finite trigram_confidence_min threshold.
    _, conf, _ = selection.propose_correction("ghbdtn")  # -> привет
    assert conf == math.inf


def test_oov_falls_through_to_ngram_delta() -> None:
    # 'ghbdtx' re-keys to 'приветч' (not a dictionary word), so the word-gate
    # does not fire and the confidence is exactly the n-gram log-prob delta.
    text = "ghbdtx"
    cand, conf, target = selection.propose_correction(text)
    assert target == "ru"
    assert not langdetect.word_known(cand, "ru")  # gate did not apply
    assert conf == langdetect.logp(cand, "ru") - langdetect.logp(text, "en")
    assert conf != math.inf


def test_real_source_word_is_not_gate_corrected() -> None:
    # A real English word is never word-gate corrected (conf != inf), even if it
    # re-keys to Cyrillic — the gate requires the original to be a non-word.
    _, conf, _ = selection.propose_correction("name")
    assert conf != math.inf
