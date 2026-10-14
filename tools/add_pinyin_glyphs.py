#!/usr/bin/env python3
"""Add the pinyin vowels a font is missing (ǐ ǒ ǖ ǘ ǚ ǜ ...) as composite glyphs.

Nunito Sans, the game's Latin UI font, has ǎ and ǔ but not the other
third-tone vowels nor ü with a tone. Every piece needed is already in the
font (dotless i, o, u, the combining caron, the stacked ü marks), so each
missing letter is built the same way the font builds its own accented
letters: base glyph + combining mark centred on half the base's advance.

It also adds the small pinyin letters (see small_pinyin.py) under their
Private Use codepoints, each one a copy of the normal letter scaled to
SCALE. Bold texts (loading screen, buttons) use these Latin fonts and the
game does not look for those codepoints in the Chinese font, so without
them the small pinyin shows as boxes there.

The result is only used to render the atlas with msdf-atlas-gen; the font
file itself is not shipped to the game.

Usage: add_pinyin_glyphs.py IN.ttf OUT.ttf
"""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent

sys.path.insert(0, str(Path(__file__).parent))
from small_pinyin import SCALE, TO_SMALL  # noqa: E402

# Character → (base glyph, [(mark glyph, extra dy), ...]).
# The dy values for ǚ/ǜ copy the font's own stacked marks: in "uni03080301"
# (ǘ's ¨+´) the dieresis sits 54 units lower and the acute 52 units higher
# than when each is used alone.
RECIPES = {
    "ǐ": ("dotlessi", [("uni030C", 0)]),
    "ǒ": ("o", [("uni030C", 0)]),
    "ǎ": ("a", [("uni030C", 0)]),
    "ǔ": ("u", [("uni030C", 0)]),
    "ě": ("e", [("uni030C", 0)]),
    "ǖ": ("u", [("uni03080304", 0)]),
    "ǘ": ("u", [("uni03080301", 0)]),
    "ǚ": ("u", [("uni0308", -54), ("uni030C", 52)]),
    "ǜ": ("u", [("uni0308", -54), ("gravecomb", 52)]),
}


def main(src, dst):
    font = TTFont(src)
    if "gvar" in font:
        font["gvar"]  # decode it now, before the glyph count changes
    cmap = font.getBestCmap()
    glyf, hmtx = font["glyf"], font["hmtx"]
    order = list(font.getGlyphOrder())
    added = []
    for char, (base, marks) in RECIPES.items():
        if ord(char) in cmap:
            continue
        missing = [g for g in [base] + [m for m, _ in marks] if g not in glyf]
        if missing:
            print(f"skip {char}: font has no {missing}")
            continue
        name = f"uni{ord(char):04X}"
        advance = hmtx[base][0]
        glyph = Glyph()
        glyph.numberOfContours = -1  # composite
        glyph.components = []
        for component, x, y in [(base, 0, 0)] + [(m, advance // 2, dy) for m, dy in marks]:
            comp = GlyphComponent()
            comp.glyphName, comp.x, comp.y, comp.flags = component, x, y, 0x4  # ROUND_XY_TO_GRID
            glyph.components.append(comp)
        glyf[name] = glyph  # also appends the name to glyf's glyph order
        if name not in order:
            order.append(name)
        glyph.recalcBounds(glyf)
        hmtx[name] = (advance, glyph.xMin)
        if "gvar" in font:  # variable font: the new glyph just follows its components
            font["gvar"].variations[name] = []
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[ord(char)] = name
        added.append(char)
    # Small letters: the normal glyph as a single component scaled by SCALE.
    cmap = font.getBestCmap()
    for char, code in TO_SMALL.items():
        if ord(char) not in cmap or ord(code) in cmap:
            continue
        base = cmap[ord(char)]
        name = f"uni{ord(code):04X}"
        comp = GlyphComponent()
        comp.glyphName, comp.x, comp.y, comp.flags = base, 0, 0, 0x4
        comp.transform = [[SCALE, 0], [0, SCALE]]
        glyph = Glyph()
        glyph.numberOfContours = -1
        glyph.components = [comp]
        glyf[name] = glyph
        if name not in order:
            order.append(name)
        glyph.recalcBounds(glyf)
        hmtx[name] = (round(hmtx[base][0] * SCALE), glyph.xMin)
        if "gvar" in font:
            font["gvar"].variations[name] = []
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[ord(code)] = name
        added.append(code)
    font.setGlyphOrder(order)
    glyf.glyphOrder = order
    font["maxp"].numGlyphs = len(order)
    font.save(dst)
    small = sum(c in TO_SMALL.values() for c in added)
    print(f"{src}: added {''.join(c for c in added if c not in TO_SMALL.values()) or 'no vowels'}"
          f" and {small} small pinyin letters")


if __name__ == "__main__":
    main(*sys.argv[1:3])
