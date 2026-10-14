"""Small pinyin letters for the Chinese font (shared by the font build and the layout).

Hytale's tooltip text has no font-size markup, so to make pinyin smaller
than the characters we add a second, scaled-down copy of every pinyin
letter to the Chinese font atlas, under Private Use Area codepoints
(U+E100 onwards, which no real text uses). Writing pinyin with those
codepoints draws it at SCALE times the normal size.
"""
SCALE = 0.7
BASE = 0xE100
LETTERS = "abcdefghijklmnopqrstuvwxyz" "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü" "ḿńňǹêʼ'"
TO_SMALL = {c: chr(BASE + i) for i, c in enumerate(LETTERS)}


def small(text):
    """Pinyin -> the same pinyin in small letters (unknown characters stay as they are)."""
    return "".join(TO_SMALL.get(c, c) for c in text)
