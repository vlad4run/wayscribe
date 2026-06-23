"""propose_correction: direction, confidence, pass-through (pure, no I/O)."""
from __future__ import annotations

from wayscribe import selection


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


def test_no_letters_is_noop() -> None:
    cand, conf, target = selection.propose_correction("12 34")
    assert cand == "12 34"
    assert conf == 0.0
    assert target is None
