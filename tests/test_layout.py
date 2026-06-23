"""Static ЙЦУКЕН↔QWERTY keymap: known words, round-trip, pass-through."""
from __future__ import annotations

import pytest

from wayscribe import layout


@pytest.mark.parametrize(
    ("typed", "meant"),
    [
        ("ghbdtn", "привет"),
        ("Ghbdtn", "Привет"),
        ("rjirf", "кошка"),
    ],
)
def test_en_to_ru_known_words(typed: str, meant: str) -> None:
    assert layout.en_to_ru(typed) == meant


@pytest.mark.parametrize(
    ("typed", "meant"),
    [
        ("руддщ", "hello"),
        ("Руддщ", "Hello"),
        ("цщкдв", "world"),
    ],
)
def test_ru_to_en_known_words(typed: str, meant: str) -> None:
    assert layout.ru_to_en(typed) == meant


@pytest.mark.parametrize(
    "latin",
    ["ghbdtn", "Hello, World!", "a/b.c,d;e'f[g]", "`~"],
)
def test_round_trip_latin(latin: str) -> None:
    # For Latin input the two maps are mutual inverses: re-key to Cyrillic and
    # back is the identity (every glyph is in the bijective set or passes through).
    assert layout.ru_to_en(layout.en_to_ru(latin)) == latin


@pytest.mark.parametrize(
    "cyr",
    ["привет", "Мир, дом!", "ёЁ"],
)
def test_round_trip_cyrillic(cyr: str) -> None:
    assert layout.en_to_ru(layout.ru_to_en(cyr)) == cyr


def test_digits_and_space_pass_through() -> None:
    assert layout.en_to_ru("1 2 3") == "1 2 3"
    assert layout.ru_to_en("1 2 3") == "1 2 3"
