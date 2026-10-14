#!/usr/bin/env bash
# Rebuild one of Hytale's Latin MSDF font atlases with the pinyin vowels added.
#
# The game's atlases are 512x512 and ~96% full, so the extra glyphs only fit
# if the whole atlas is repacked at a slightly smaller pixel size (e.g. 18.4
# instead of 18.546875 px/em). MSDF scales cleanly, so on screen the text
# keeps its size and the 1% resolution change is not visible.
#
# Usage: rebuild_font_atlas.sh MSDF_ATLAS_GEN GAME_FONTS_DIR FONT_NAME OUT_DIR
#   e.g. rebuild_font_atlas.sh ./msdf-atlas-gen ".../Client/Data/Shared/UI/Fonts" NunitoSans-Medium out
set -euo pipefail
GEN=$1; FONTS=$2; NAME=$3; OUT=$4
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
mkdir -p "$OUT"

# 1. Font with the missing pinyin vowels built from its own pieces.
python3 "$HERE/add_pinyin_glyphs.py" "$FONTS/$NAME.ttf" "$WORK/font.ttf"

# 2. Same characters as the original atlas, plus every pinyin vowel and small letter the font now has.
python3 - "$FONTS/$NAME.json" "$WORK/font.ttf" "$WORK/charset.txt" "$WORK/params" <<'PY'
import json, sys
from fontTools.ttLib import TTFont
atlas = json.load(open(sys.argv[1], encoding="utf-8"))
cmap = TTFont(sys.argv[2]).getBestCmap()
pinyin = "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü" + "".join(map(chr, range(0xE100, 0xE200)))  # + small letters
codes = {g["unicode"] for g in atlas["glyphs"]} | {ord(c) for c in pinyin if ord(c) in cmap}
open(sys.argv[3], "w").write(", ".join(map(str, sorted(codes))))
a = atlas["atlas"]
open(sys.argv[4], "w").write(f'{a["type"]} {a["distanceRange"]} {a["size"]} {a["width"]} {a["height"]} {a["yOrigin"]}\n')
PY
read -r TYPE RANGE SIZE WIDTH HEIGHT YORIGIN < "$WORK/params"

# 3. Repack, lowering the pixel size in small steps until everything fits.
size=$SIZE
while :; do
  log=$("$GEN" -font "$WORK/font.ttf" -charset "$WORK/charset.txt" -type "$TYPE" -pxrange "$RANGE" \
          -size "$size" -yorigin "$YORIGIN" -pxalign on -dimensions "$WIDTH" "$HEIGHT" \
          -format png -imageout "$OUT/$NAME.png" -json "$OUT/$NAME.json" 2>&1) || true
  if grep -q 'Could not fit' <<<"$log"; then
    size=$(python3 -c "print(round($size - 0.05, 4))")
  elif [[ -f "$OUT/$NAME.json" ]]; then
    break
  else
    echo "$log" >&2; exit 1
  fi
done
echo "$NAME: rebuilt at $size px/em (original $SIZE)"
