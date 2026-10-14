#!/usr/bin/env python3
"""Builds HytalePinyin's glossary and game texts from the game's own files.

    python3 glossary/build.py --game "%APPDATA%/Hytale/install/release/package/game/latest" \\
        --vividhanzi ../VividHanzi --hanzidict ../HanziDict/v1

Steps:
  1. Read every item's name and description (en-US and zh-CN) from Assets.zip.
  2. Send the Chinese texts to VividHanzi's "hytale" exporter, which splits them
     into words and gives each word its pinyin with the app's own pipeline
     (CC-CEDICT + pinyin-pro, 一/不 tone sandhi, polyphonic characters). Word
     frequencies from wordfreq go with them, so it splits each text into its
     most likely words (在 · 地图, not 在地 · 图).
  3. Apply our two hand-edited files:
       game-terms.tsv  words the dictionary doesn't have (水蓝石 shuǐ lán shí),
                       used when splitting the texts.
       fixes.tsv       the right reading for a word the pipeline wasn't sure of
                       (review.tsv lists them), used wherever it is unsure of it.
  4. Write, in out/:
       glossary.tsv    one row per item: ID, English, Chinese, pinyin, words, flags.
       review.tsv      readings the pipeline wasn't sure of, most frequent first.
       items.json      each item's annotated texts, for the plugin.
       breakdown.json  dictionary entries of every word and character used, plus HSK 1-4.
       lang/zh-CN[.tones][.english].lang, the tooltip texts in each of the
                       four combinations of tone colours and English, plus menu labels.
       client/zh-CN/client.lang, the client's menus with pinyin (see ui.py).
       ui-labels.tsv   every menu label and its pinyin version.

Nothing here is translated by hand: Chinese and English texts are the game's
official ones, and readings come from the dictionary unless fixes.tsv says otherwise.
"""
import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gamedata import load_items, parse_description, parse_lang, read_item_keys, read_lang  # noqa: E402
from render import GREY, Metrics, color, colored_pinyin, plain_pinyin, ruby_lines  # noqa: E402
from wordfreq import get_frequency_dict  # noqa: E402

from ui import chinese_parts, client_labels, label_with_pinyin, patch_lang_file, server_labels, with_pinyin  # noqa: E402


# The plugin picks one of these per player: tone colours on/off x English on/off.
# Plain zh-CN.lang is the default everyone gets until they change a setting.
VARIANTS = {
    "zh-CN.lang": (False, False),
    "zh-CN.english.lang": (False, True),
    "zh-CN.tones.lang": (True, False),
    "zh-CN.tones.english.lang": (True, True),
}


def read_tsv(path):
    """Rows of a hand-edited TSV file, skipping the header and # comments."""
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        rows = [r for r in csv.reader(f, delimiter="\t") if r and not r[0].startswith("#")]
    return rows[1:]


def has_han(text):
    return any("㐀" <= c <= "鿿" for c in text)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", help="the game folder (has Assets.zip and Client/)")
    ap.add_argument("--lang", help="instead of --game: a folder with <locale>/server.lang")
    ap.add_argument("--font", help="instead of --game: NotoSansSC-Medium.ttf")
    ap.add_argument("--client-lang", help="instead of --game: the client's zh-CN/client.lang")
    ap.add_argument("--vividhanzi", required=True, help="a VividHanzi checkout (with npm ci done)")
    ap.add_argument("--hanzidict", required=True, help="the v1 folder of a HanziDict checkout")
    ap.add_argument("--item-keys", help="item-keys.tsv written by the plugin (which keys each item uses)")
    ap.add_argument("--out", default=str(HERE / "out"))
    args = ap.parse_args()

    game = Path(args.game) if args.game else None
    lang_source = game / "Assets.zip" if game else Path(args.lang)
    font = game / "Client/Data/Shared/UI/Fonts/NotoSansSC-Medium.ttf" if game else Path(args.font)
    client_lang = game / "Client/Data/Shared/Language/zh-CN/client.lang" if game else Path(args.client_lang)
    out = Path(args.out)
    (out / "lang").mkdir(parents=True, exist_ok=True)

    # 1. Game texts. Each description line becomes plain text + colours.
    items = load_items(lang_source, read_item_keys(args.item_keys) if args.item_keys else None)
    # A description shared by several items can't start with one item's name
    description_users = Counter(item.description_key for item in items)
    written = set()  # keys already written (several items can share one)
    texts = []
    for item in items:
        if item.zh_name:
            texts.append(item.zh_name)
        for paragraph in parse_description(item.zh_description):
            texts += [piece for line in paragraph for piece in line.pieces if has_han(piece)]
    # Menus and other short labels (ui.py)
    ui_server = server_labels(read_lang(lang_source, "zh-CN"))
    client_text = client_lang.read_text(encoding="utf-8")
    ui_client = client_labels(parse_lang(client_text))
    texts += [part for text in [*ui_server.values(), *ui_client.values()] for part in chinese_parts(text)]
    (out / "texts.json").write_text(json.dumps(sorted(set(texts)), ensure_ascii=False), encoding="utf-8")

    # 2. VividHanzi's exporter, with our game terms as extra words and the
    #    frequency of every piece of text that wordfreq knows as a word.
    terms = [{"hanzi": h, "pinyin": p, "en": e} for h, p, e, *_ in read_tsv(HERE / "game-terms.tsv")]
    (out / "extra-words.json").write_text(json.dumps(terms, ensure_ascii=False), encoding="utf-8")
    wordfreq = get_frequency_dict("zh", wordlist="best")
    frequencies = {text[i:j]: wordfreq[text[i:j]] for text in set(texts) for i in range(len(text))
                   for j in range(i + 1, min(i + 9, len(text) + 1)) if text[i:j] in wordfreq}
    (out / "frequencies.json").write_text(json.dumps(frequencies, ensure_ascii=False), encoding="utf-8")
    export_path = out / "vividhanzi-export.json"
    subprocess.run(["node", "scripts/hytale/export.ts", "--texts", (out / "texts.json").resolve(),
                    "--dictionary", Path(args.hanzidict).resolve(), "--extra-words", (out / "extra-words.json").resolve(),
                    "--frequencies", (out / "frequencies.json").resolve(),
                    "--out", export_path.resolve()], cwd=args.vividhanzi, check=True)
    export = json.loads(export_path.read_text(encoding="utf-8"))

    # 3. Hand fixes: word -> reading, where the pipeline was unsure.
    fixes = {h: p for h, p, *_ in read_tsv(HERE / "fixes.tsv")}
    term_set = {t["hanzi"] for t in terms}
    uncertain = Counter()
    uncertain_where = defaultdict(list)

    def annotate(text, item_id):
        """[(hanzi, pinyin or None)] for a text, with fixes applied and doubts recorded."""
        words = []
        for entry in export["texts"][text]:
            hanzi, pinyin = entry[0], (entry[1] if len(entry) > 1 else None)
            # Fixes only apply where the pipeline was unsure: 长 is cháng in 长管
            # but zhǎng inside 成长, and there the dictionary already knows it.
            if len(entry) == 3 and hanzi in fixes:
                pinyin = fixes[hanzi]
            elif len(entry) == 3:
                uncertain[(hanzi, pinyin)] += 1
                if len(uncertain_where[(hanzi, pinyin)]) < 3:
                    uncertain_where[(hanzi, pinyin)].append(f"{item_id}: {text}")
            words.append((hanzi, pinyin))
        return words

    # 4. Outputs.
    metrics = Metrics(font)
    glossary, data = [], {}
    lang = {name: [] for name in VARIANTS}
    for item in items:
        flags = []
        if not item.zh_name:
            flags.append("no-official-chinese")
            glossary.append([item.id, item.en_name, "", "", "", " ".join(flags)])
            continue
        name_words = annotate(item.zh_name, item.id)
        if any(h in term_set for h, _ in name_words):
            flags.append("game-term")
        if any(e[2:] for e in export["texts"][item.zh_name] if e[0] not in fixes):
            flags.append("check-reading")
        glossary.append([item.id, item.en_name, item.zh_name, plain_pinyin(name_words),
                         " · ".join(f"{h} {p}" if p else h for h, p in name_words), " ".join(flags)])

        zh_paragraphs = parse_description(item.zh_description)
        # English lines lose their colours (grey instead) but keep italics
        en_paragraphs = [[{"text": line.text or re.sub(r"<[^>]+>", "", line.raw), "italic": line.italic}
                          for line in paragraph] for paragraph in parse_description(item.en_description)]
        record = {"nameKey": item.name_key, "descriptionKey": item.description_key, "en": item.en_name, "zh": item.zh_name, "words": name_words, "description": []}
        for paragraph in zh_paragraphs:
            lines = []
            for line in paragraph:
                if line.raw or not has_han(line.text):
                    lines.append({"raw": line.raw or line_markup(line)})
                else:
                    words = [w for piece in line.pieces
                             for w in (annotate(piece, item.id) if has_han(piece) else [(piece, None)])]
                    lines.append({"words": words, "colors": line.colors, "italic": line.italic})
            record["description"].append(lines)
        record["descriptionEn"] = en_paragraphs
        data[item.id] = record

        # small pinyin, like the menus: the name also shows up in them ("按 F 收获浆果灌木")
        title = with_pinyin(item.zh_name, plain_pinyin(name_words))
        own_description = description_users[item.description_key] == 1
        record["sharedDescription"] = not own_description
        for variant, (tones, english) in VARIANTS.items():
            if item.name_key not in written:
                # the title can't be coloured, so the English name just follows
                lang[variant].append(f"{item.name_key} = {title} · {item.en_name}" if english else f"{item.name_key} = {title}")
            if not item.description_key or item.description_key in written:
                continue  # some items have no description key at all
            body = description_text(record, metrics, english, tones)
            if own_description:
                head = colored_pinyin(name_words, tones=tones) + (f"\\n{color(item.en_name, GREY)}" if english else "")
                body = head + (f"\\n\\n{body}" if body else "")
            if body:
                lang[variant].append(f"{item.description_key} = {body}")
        written |= {item.name_key, item.description_key}

    # Labels: server ones go with the item texts (same in every variant); the
    # client file is patched as a whole, for the installer to put in the game.
    # In the English variants server labels get the English text too
    # ("罕见 (hǎnjiàn) · Uncommon"); client ones can't, the file is the same for everyone.
    en_server = read_lang(lang_source, "en-US")
    ui_rows = []
    for key, text in ui_server.items():
        if key not in written:
            labelled = label_with_pinyin(text, lambda part: plain_pinyin(annotate(part, f"ui:{key}")))
            ui_rows.append([key, text, labelled])
            en = en_server.get(key, "")
            for variant, (_, english) in VARIANTS.items():
                # not for texts with placeholders: {name} would be filled with
                # the Chinese name and its English twice over
                with_en = english and en and "<" not in en and "\\n" not in en and "{" not in en
                lang[variant].append(f"{key} = {labelled} · {en}" if with_en else f"{key} = {labelled}")
    client_patch = {}
    for key, text in ui_client.items():
        client_patch[key] = label_with_pinyin(text, lambda part: plain_pinyin(annotate(part, f"client:{key}")))
        ui_rows.append([key, text, client_patch[key]])
    (out / "client" / "zh-CN").mkdir(parents=True, exist_ok=True)
    (out / "client" / "zh-CN" / "client.lang").write_text(patch_lang_file(client_text, client_patch), encoding="utf-8")
    write_tsv(out / "ui-labels.tsv", ["key", "chinese", "with pinyin"], ui_rows)

    write_tsv(out / "glossary.tsv", ["id", "english", "chinese", "pinyin", "words", "flags"], glossary)
    write_tsv(out / "review.tsv", ["word", "pinyin", "count", "examples"],
              [[h, p, n, " | ".join(uncertain_where[(h, p)])] for (h, p), n in uncertain.most_common()])
    (out / "items.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    breakdown = {k: v for k, v in export.items() if k != "texts"}
    (out / "breakdown.json").write_text(json.dumps(breakdown, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for name, lines in lang.items():
        header = "# Generated by HytalePinyin glossary/build.py from the game's official texts. Do not edit by hand.\n"
        (out / "lang" / name).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")

    with_zh = sum(1 for row in glossary if row[2])
    print(f"{len(items)} items, {with_zh} with Chinese; {len(ui_rows)} menu labels; {len(uncertain)} uncertain readings to review "
          f"({sum(uncertain.values())} places) -> {out}")


def line_markup(line):
    """A parsed line back to markup (for lines without Chinese)."""
    from render import colored_hanzi
    text = colored_hanzi(line.text, line.colors)
    return f"<i>{text}</i>" if line.italic else text


def description_text(record, metrics, english, tones):
    """The description: each Chinese line as pinyin-over-hanzi, and in the English
    variant each paragraph followed by the game's English one in grey."""
    zh, en = record["description"], record["descriptionEn"]
    paired = english and len(zh) == len(en)
    out = []
    for i, paragraph in enumerate(zh):
        lines = []
        for line in paragraph:
            if "raw" in line:
                lines.append(line["raw"])
                continue
            # ruby_lines alternates pinyin and hanzi; only the hanzi take the
            # paragraph's italics, the pinyin stays upright to be easy to read
            for n, text in enumerate(ruby_lines(line["words"], line["colors"], metrics, tones=tones)):
                lines.append(f"<i>{text}</i>" if line["italic"] and n % 2 and text else text)
        if paired:
            lines += [grey_line(text) for text in en[i]]
        out.append("\\n".join(lines))
    if english and not paired and en:  # no Chinese (or paragraphs don't match): English after it
        out.append("\\n".join(grey_line(text) for p in en for text in p))
    return "\\n\\n".join(out)


def grey_line(line):
    """An English line in grey, in italics if the game has it in italics."""
    text = color(line["text"], GREY) if line["text"] else ""
    return f"<i>{text}</i>" if line["italic"] and text else text


def write_tsv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


if __name__ == "__main__":
    main()
