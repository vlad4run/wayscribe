"""Static ЙЦУКЕН↔QWERTY keymap for layout-mismatch correction.

Pure, dependency-free, char-by-char. Maps the *physical key* a user pressed to
the glyph the other layout would have produced. Only the bijective letter and
punctuation positions are mapped; digits, spaces and anything else pass through
unchanged, which keeps `en_to_ru`/`ru_to_en` mutual inverses on every input.

The number-row shifted symbols (`@`, `№`, `:` via Shift+digit, …) are *not*
mapped: they sit on different physical keys between the two layouts, so they
have no clean 1:1 correspondence and would break the round-trip invariant.
"""
from __future__ import annotations

# US-QWERTY glyph -> the glyph the ЙЦУКЕН layout emits on the same physical key.
# Lowercase + their Shifted forms; both directions stay bijective.
_EN_TO_RU: dict[str, str] = {
    # top letter row
    "q": "й", "w": "ц", "e": "у", "r": "к", "t": "е", "y": "н",
    "u": "г", "i": "ш", "o": "щ", "p": "з", "[": "х", "]": "ъ",
    # home row
    "a": "ф", "s": "ы", "d": "в", "f": "а", "g": "п", "h": "р",
    "j": "о", "k": "л", "l": "д", ";": "ж", "'": "э",
    # bottom row
    "z": "я", "x": "ч", "c": "с", "v": "м", "b": "и", "n": "т",
    "m": "ь", ",": "б", ".": "ю", "/": ".",
    # backtick
    "`": "ё",
    # uppercase letter rows
    "Q": "Й", "W": "Ц", "E": "У", "R": "К", "T": "Е", "Y": "Н",
    "U": "Г", "I": "Ш", "O": "Щ", "P": "З", "{": "Х", "}": "Ъ",
    "A": "Ф", "S": "Ы", "D": "В", "F": "А", "G": "П", "H": "Р",
    "J": "О", "K": "Л", "L": "Д", ":": "Ж", '"': "Э",
    "Z": "Я", "X": "Ч", "C": "С", "V": "М", "B": "И", "N": "Т",
    "M": "Ь", "<": "Б", ">": "Ю", "?": ",",
    "~": "Ё",
}

_RU_TO_EN: dict[str, str] = {v: k for k, v in _EN_TO_RU.items()}


def en_to_ru(text: str) -> str:
    """Re-key Latin glyphs as if typed on the Russian layout (`ghbdtn`→`привет`)."""
    return "".join(_EN_TO_RU.get(ch, ch) for ch in text)


def ru_to_en(text: str) -> str:
    """Re-key Cyrillic glyphs as if typed on the US layout (`руддщ`→`hello`)."""
    return "".join(_RU_TO_EN.get(ch, ch) for ch in text)
