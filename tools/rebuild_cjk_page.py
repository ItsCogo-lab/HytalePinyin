#!/usr/bin/env python3
"""Add pinyin to the Chinese font (NotoSansSC-Medium) used by the zh-CN client.

The font is split into 71 MSDF pages (_01.._71, 512x512 each). No page has
the toned vowels, so the game borrowed them from NunitoSans and they looked
like a different font. The last page only has 41 glyphs, so we rebuild it
with:
  1. the pinyin vowels at normal size (ā, ǎ, ü ...), and
  2. a small copy of every pinyin letter under Private Use Area codepoints
     (see small_pinyin.py), used to put small pinyin above the characters.

msdf-atlas-gen picks the largest glyph size that fits 512x512, the same way
the game's own pages were made. The small copies are drawn at full size and
then shrunk in the JSON (advance and plane bounds times SCALE), so they keep
the same sharpness as everything else.

Usage: rebuild_cjk_page.py MSDF_ATLAS_GEN GAME_FONTS_DIR OUT_DIR
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).parent))
from small_pinyin import SCALE, TO_SMALL  # noqa: E402

NAME, PAGE = "NotoSansSC-Medium", "NotoSansSC-Medium_71"
VOWELS = "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜüĀÁǍÀĒÉĚÈĪÍǏÌŌÓǑÒŪÚǓÙǕǗǙǛÜêÊḿńňǹ·"


def main(gen, fonts_dir, out_dir):
    fonts_dir, out = Path(fonts_dir), Path(out_dir) / NAME
    out.mkdir(parents=True, exist_ok=True)
    page = json.loads((fonts_dir / NAME / f"{PAGE}.json").read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory() as tmp:
        # Font copy where each small codepoint points at the normal letter's glyph.
        font = TTFont(fonts_dir / f"{NAME}.ttf")
        cmap = font.getBestCmap()
        small = {ord(s): cmap[ord(c)] for c, s in TO_SMALL.items() if ord(c) in cmap}
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap.update(small)
        ttf = Path(tmp) / "font.ttf"
        font.save(ttf)

        codes = [g["unicode"] for g in page["glyphs"]]
        codes += [ord(c) for c in VOWELS if ord(c) in cmap and ord(c) not in codes]
        codes += sorted(small)
        charset = Path(tmp) / "charset.txt"
        charset.write_text(", ".join(map(str, codes)))

        log = subprocess.run([gen, "-font", ttf, "-charset", charset, "-type", "msdf", "-pxrange", "8",
                              "-yorigin", "top", "-pxalign", "on", "-dimensions", "512", "512",
                              "-format", "png", "-imageout", out / f"{PAGE}.png", "-json", out / f"{PAGE}.json"],
                             capture_output=True, text=True, check=True)
        print(*[l for l in (log.stdout + log.stderr).splitlines() if "Glyph size" in l])

    # Shrink the small copies. y grows downwards (yorigin top) and 0 is the
    # baseline, so scaling around 0 keeps them sitting on the baseline.
    atlas = json.loads((out / f"{PAGE}.json").read_text(encoding="utf-8"))
    for g in atlas["glyphs"]:
        if g["unicode"] in small:
            g["advance"] *= SCALE
            if "planeBounds" in g:
                g["planeBounds"] = {k: v * SCALE for k, v in g["planeBounds"].items()}
    (out / f"{PAGE}.json").write_text(json.dumps(atlas, separators=(",", ":")), encoding="utf-8")
    print(f"{PAGE}: {len(atlas['glyphs'])} glyphs, {len(small)} small pinyin letters")


if __name__ == "__main__":
    main(*sys.argv[1:4])
