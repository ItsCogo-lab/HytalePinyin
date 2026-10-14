"""Turning annotated words into Hytale tooltip text.

A "word" here is what the VividHanzi exporter returns for a piece of text:
(hanzi, pinyin) with the pinyin as space-separated syllables ("gōng zuò tái"),
or (symbols, None) for punctuation and anything that has no reading.

The tooltip only supports colours and italics: no font sizes and no
positioning. Pinyin above the characters ("ruby") is faked with two lines,
pinyin on top and hanzi below, lined up with spaces. We know how wide every
glyph is (the font's advance widths, the same numbers the game's MSDF atlas
uses), so each word is padded with normal spaces until both lines reach the
same x position. The pinyin is written with the small letters that
tools/rebuild_cjk_page.py adds to the Chinese font (see small_pinyin.py), so
it takes less room. Lines are broken by us, before the tooltip's own wrap
width; otherwise the game would wrap the two lines separately.
"""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from small_pinyin import SCALE, TO_SMALL, small  # noqa: E402

# Same colours as VividHanzi's dark theme (src/index.css); 5 is the neutral tone.
TONE_COLORS = {1: "#f27272", 2: "#f0a347", 3: "#6cc97c", 4: "#6fa9f5", 5: "#a0a4ab"}
GREY = "#a0a4ab"
TONE_MARKS = {c: t for t, chars in {1: "āēīōūǖ", 2: "áéíóúǘ", 3: "ǎěǐǒǔǚ", 4: "àèìòùǜ"}.items()
              for c in chars + chars.upper()}
FROM_SMALL = {s: c for c, s in TO_SMALL.items()}
WRAP_EM = 28  # the tooltip wraps at about 30 full-width characters


def tone(syllable):
    """1-4 from the tone mark, 5 (neutral) if it has none."""
    return next((TONE_MARKS[FROM_SMALL.get(c, c)] for c in syllable if FROM_SMALL.get(c, c) in TONE_MARKS), 5)


def join_syllables(pinyin):
    """'xī ān' -> "xī'ān": one word, with the apostrophe pinyin uses before a, o, e."""
    out = ""
    for i, syllable in enumerate(pinyin.split()):
        plain = syllable.lower().translate(str.maketrans("āáǎàōóǒòēéěè", "aaaaooooeeee"))
        out += ("'" if i and plain[:1] in "aoe" else "") + syllable
    return out


def plain_pinyin(words):
    """Pinyin of a whole text, words separated by spaces: 'shuǐlánshí liáng'."""
    return " ".join(join_syllables(p) for _, p in words if p)


def colored_pinyin(words, use_small=False, tones=True):
    """Pinyin of a text, words separated by spaces, each syllable in its tone
    colour unless `tones` is off (then it takes the text's normal colour)."""
    parts = []
    for _, pinyin in words:
        if not pinyin:
            continue
        syllables = pinyin.split()
        joined = join_syllables(pinyin)
        # colour each syllable inside the joined word (the apostrophe stays uncoloured)
        size = small if use_small else (lambda text: text)
        out, rest = "", joined
        for s in syllables:
            start = rest.index(s)
            out += size(rest[:start]) + color(size(s), TONE_COLORS[tone(s)] if tones else None)
            rest = rest[start + len(s):]
        parts.append(out + size(rest))
    return " ".join(parts)


def color(text, hex_color):
    return f'<color is="{hex_color}">{text}</color>' if hex_color else text


class Metrics:
    """Advance widths in em, read from the game's Chinese font (NotoSansSC-Medium.ttf)."""

    def __init__(self, ttf_path):
        font = TTFont(ttf_path)
        self.cmap = font.getBestCmap()
        self.hmtx = font["hmtx"]
        self.upem = font["head"].unitsPerEm

    def width(self, text):
        """Width in em. Small pinyin letters count as SCALE times the normal letter."""
        total = 0.0
        for c in text:
            normal = FROM_SMALL.get(c, c)
            glyph = self.cmap.get(ord(normal))
            advance = self.hmtx[glyph][0] / self.upem if glyph else 1.0
            total += advance * (SCALE if c in FROM_SMALL else 1)
        return total


def ruby_lines(words, colors, metrics, width=WRAP_EM, tones=True):
    """Pinyin-over-hanzi lines for one line of text.

    words: [(hanzi, pinyin or None)], colors: the colour of each character of
    the text (None = default). Returns the tooltip lines, pinyin and hanzi
    alternating. Punctuation sticks to the word before it, so a line never
    starts with "。".
    """
    # cells: (hanzi, pinyin syllables, trailing symbols, colours of hanzi + symbols)
    cells, pos = [], 0
    for hanzi, pinyin in words:
        cols = colors[pos:pos + len(hanzi)]
        pos += len(hanzi)
        if pinyin is None and cells:
            h, s, tail, c = cells[-1]
            cells[-1] = (h, s, tail + hanzi, c + cols)
        else:
            cells.append((hanzi, pinyin.split() if pinyin else [], "", cols))

    space = metrics.width(" ")
    sized = []
    for hanzi, syllables, tail, cols in cells:
        top = small(join_syllables(" ".join(syllables))) if syllables else ""
        sized.append((hanzi, syllables, tail, cols, metrics.width(hanzi), metrics.width(top), metrics.width(tail)))

    # break into rows that fit
    rows, row, x = [], [], 0.0
    for cell in sized:
        w = max(cell[4] + cell[6], cell[5])
        if row and x + w > width:
            rows.append(row)
            row, x = [], 0.0
        row.append(cell)
        x += w + space
    if row:
        rows.append(row)

    lines = []
    for row in rows:
        top, bottom = "", ""
        x_top = x_bottom = col = 0.0  # where each line really is, and where the column starts
        for hanzi, syllables, tail, cols, wh, wp, wt in row:
            w = max(wh, wp)
            # centre the narrower of the two inside the column; rounding against
            # the column's absolute position keeps errors from piling up
            pad_top = max(round((col + (w - wp) / 2 - x_top) / space), 0)
            pad_bottom = max(round((col + (w - wh) / 2 - x_bottom) / space), 0)
            if syllables:
                top += " " * pad_top + colored_pinyin([(hanzi, " ".join(syllables))], use_small=True, tones=tones)
                x_top += pad_top * space + wp
            bottom += " " * pad_bottom + colored_hanzi(hanzi + tail, cols)
            x_bottom += pad_bottom * space + wh + wt
            col += max(w, (w + wh) / 2 + wt) + space
        lines += [top.rstrip(), bottom.rstrip()]
    return lines


def colored_hanzi(text, colors):
    """Text with the original colour spans put back."""
    out, i = "", 0
    while i < len(text):
        j = i
        while j < len(text) and colors[j] == colors[i]:
            j += 1
        out += color(text[i:j], colors[i])
        i = j
    return out
