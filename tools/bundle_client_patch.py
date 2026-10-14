#!/usr/bin/env python3
"""Put the client patch inside the plugin, for it to install itself.

The CurseForge app only copies the mod's JAR into the Mods folder, so the
JAR carries the client files and, in singleplayer (the server runs on the
player's own computer, next to the client), copies them into the game.
See plugin/src/.../ClientPatch.java. This writes plugin/resources/client-patch/:

  files/UI/Fonts/...         the patched font atlases (same as client-patch/Fonts)
  files/UI/Fonts/HytalePinyin-Small.ttf
                             only the small pinyin letters, as a font family of
                             their own ("HytalePinyin") that the menus fall back
                             to. A new file, so it can be written while the
                             game runs (the game keeps its own .ttf files open).
  originals.tsv              path, SHA-256 of the game's original file: an atlas
                             is only replaced if the game still has that exact
                             file, so a game update with new fonts is left alone.
  client-labels.tsv          key, official text, text with pinyin: the menu
                             labels, applied line by line to whatever
                             client.lang the game has, so new menu texts from a
                             game update are kept.

Usage: bundle_client_patch.py GAME_SHARED_DIR PATCHED_CLIENT_LANG OUT_DIR
  GAME_SHARED_DIR: the game's original Client/Data/Shared
"""
import hashlib
import shutil
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "glossary"))
from small_pinyin import TO_SMALL  # noqa: E402
from gamedata import parse_lang  # noqa: E402

PATCH = HERE.parent / "client-patch"
ATLASES = [f"UI/Fonts/{name}.{ext}" for name in ("NunitoSans-Medium", "NunitoSans-ExtraBold", "NotoSans-Bold")
           for ext in ("json", "png")]
ATLASES += ["UI/Fonts/NotoSansSC-Medium/NotoSansSC-Medium_71.json", "UI/Fonts/NotoSansSC-Medium/NotoSansSC-Medium_71.png"]
FAMILY = "HytalePinyin"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def small_font(patched_ttf, out):
    """The small letters of the patched Noto Sans SC, renamed to their own family."""
    font = TTFont(patched_ttf)
    options = subset.Options()
    options.name_IDs = ["*"]
    options.notdef_outline = True
    options.layout_features = []
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[ord(c) for c in TO_SMALL.values()])
    subsetter.subset(font)
    names = font["name"]
    for record in list(names.names):
        if record.nameID in (1, 3, 4, 6, 16, 17, 21, 22):
            names.removeNames(nameID=record.nameID)
    for name_id, value in ((1, FAMILY), (2, "Regular"), (3, f"{FAMILY}-Small"), (4, FAMILY), (6, f"{FAMILY}-Small")):
        names.setName(value, name_id, 3, 1, 0x409)
        names.setName(value, name_id, 1, 0, 0)
    font.save(out)


def main(game_shared, patched_client_lang, out_dir):
    game, out = Path(game_shared), Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    rows = []
    for rel in ATLASES:
        target = out / "files" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PATCH / "Fonts" / rel.removeprefix("UI/Fonts/"), target)
        rows.append(f"{rel}\t{sha256(game / rel)}")
    (out / "originals.tsv").write_text("path\tsha256\n" + "\n".join(rows) + "\n", encoding="utf-8")

    small_font(PATCH / "Fonts" / "NotoSansSC-Medium.ttf", out / "files" / "UI/Fonts/HytalePinyin-Small.ttf")

    original = parse_lang((game / "Language/zh-CN/client.lang").read_text(encoding="utf-8"))
    patched = parse_lang(Path(patched_client_lang).read_text(encoding="utf-8"))
    labels = [(k, original[k], v) for k, v in patched.items() if k in original and original[k] != v]
    assert not any("\t" in field or "\n" in field for row in labels for field in row)
    (out / "client-labels.tsv").write_text(
        "key\tofficial\twith pinyin\n" + "".join("\t".join(row) + "\n" for row in labels), encoding="utf-8")
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"client patch bundled: {len(ATLASES)} atlas files, small font, {len(labels)} menu labels, {size // 1024} KB")


if __name__ == "__main__":
    main(*sys.argv[1:4])
