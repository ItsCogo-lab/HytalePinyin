#!/usr/bin/env python3
"""Add the small pinyin letters to the TTF the menus fall back to.

The main menu, social panel, loading screen and other client screens are
drawn with NoesisGUI, which reads .ttf files directly, not the MSDF atlases.
Its font families (Client/Data/Shared/UI/DesignSystem/Fonts.xaml) are
"Nunito Sans" or "Lexend Bold", then Noto Sans SC, TC, JP, KR: a character
the first font lacks is taken from the next one. Every family goes through
Noto Sans SC, so adding the small letters there is enough.

Each small letter (see small_pinyin.py) is the font's own letter scaled to
SCALE, written as a plain outline (not a scaled composite) so any TrueType
reader draws it the same.

Usage: patch_ui_font.py NotoSansSC-Medium.ttf OUT.ttf
"""
import sys
from pathlib import Path

from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).parent))
from small_pinyin import SCALE, TO_SMALL  # noqa: E402


def main(src, dst):
    font = TTFont(src)
    cmap = font.getBestCmap()
    glyphs = font.getGlyphSet()
    glyf, hmtx = font["glyf"], font["hmtx"]
    vmtx = font["vmtx"] if "vmtx" in font else None
    order = list(font.getGlyphOrder())
    added = 0
    for char, code in TO_SMALL.items():
        if ord(char) not in cmap or ord(code) in cmap:
            continue
        base = cmap[ord(char)]
        pen = TTGlyphPen(glyphs)
        glyphs[base].draw(TransformPen(pen, (SCALE, 0, 0, SCALE, 0, 0)))
        name = f"uni{ord(code):04X}"
        glyph = pen.glyph()
        glyf[name] = glyph
        order.append(name)
        glyph.recalcBounds(glyf)
        hmtx[name] = (round(hmtx[base][0] * SCALE), glyph.xMin if glyph.numberOfContours else 0)
        if vmtx is not None:
            vmtx[name] = vmtx[base]
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[ord(code)] = name
        added += 1
    font.setGlyphOrder(order)
    glyf.glyphOrder = order
    font["maxp"].numGlyphs = len(order)
    font.save(dst)
    print(f"{src}: added {added} small pinyin letters")


if __name__ == "__main__":
    main(*sys.argv[1:3])
