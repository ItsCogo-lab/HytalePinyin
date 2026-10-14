#!/usr/bin/env python3
"""Render a line of text from an MSDF atlas (JSON + PNG) to a PNG, to check glyphs.

It follows the usual MSDF shader: sample the atlas, take the median of the
three channels and turn the distance into coverage. Good enough to see
whether a glyph exists and looks right, not a pixel-exact copy of the game.

Usage: preview_atlas.py ATLAS.json ATLAS.png "text" OUT.png [font_px]
"""
import json
import sys

import numpy as np
from PIL import Image


def render(meta, atlas, text, px):
    glyphs = {g["unicode"]: g for g in meta["glyphs"]}
    m = meta["metrics"]
    asc = -m["ascender"] if meta["atlas"]["yOrigin"] == "top" else m["ascender"]
    height = int(px * m["lineHeight"]) + 8
    width = int(px * sum(glyphs.get(ord(c), {"advance": 0.5})["advance"] for c in text)) + 16
    out = np.zeros((height, width), dtype=np.float32)
    screen_range = meta["atlas"]["distanceRange"] * px / meta["atlas"]["size"]
    pen_x, base_y = 8.0, 4 + asc * px
    for ch in text:
        g = glyphs.get(ord(ch))
        if g is None:  # what the game shows instead: a "?"
            g = glyphs[ord("?")]
        if "planeBounds" in g:
            pb, ab = g["planeBounds"], g["atlasBounds"]
            x0, x1 = pen_x + pb["left"] * px, pen_x + pb["right"] * px
            y0, y1 = base_y + pb["top"] * px, base_y + pb["bottom"] * px
            for y in range(max(0, int(y0)), min(height, int(np.ceil(y1)))):
                for x in range(max(0, int(x0)), min(width, int(np.ceil(x1)))):
                    u = ab["left"] + (x + 0.5 - x0) / (x1 - x0) * (ab["right"] - ab["left"])
                    v = ab["top"] + (y + 0.5 - y0) / (y1 - y0) * (ab["bottom"] - ab["top"])
                    s = bilinear(atlas, u - 0.5, v - 0.5)
                    sd = np.median(s) / 255.0
                    out[y, x] = max(out[y, x], np.clip((sd - 0.5) * screen_range + 0.5, 0, 1))
        pen_x += g["advance"] * px
    return Image.fromarray((255 - out * 255).astype(np.uint8))


def bilinear(img, x, y):
    h, w = img.shape[:2]
    x0, y0 = int(np.floor(x)), int(np.floor(y))
    fx, fy = x - x0, y - y0
    def px(xx, yy):
        return img[min(max(yy, 0), h - 1), min(max(xx, 0), w - 1)].astype(np.float32)
    return ((px(x0, y0) * (1 - fx) + px(x0 + 1, y0) * fx) * (1 - fy)
            + (px(x0, y0 + 1) * (1 - fx) + px(x0 + 1, y0 + 1) * fx) * fy)


if __name__ == "__main__":
    meta = json.load(open(sys.argv[1], encoding="utf-8"))
    atlas = np.array(Image.open(sys.argv[2]).convert("RGB"))
    size = float(sys.argv[5]) if len(sys.argv) > 5 else 40
    render(meta, atlas, sys.argv[3], size).save(sys.argv[4])
