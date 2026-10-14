"""Reading Hytale's item texts (names and descriptions) from the game's .lang files.

The texts live in Assets.zip, in Server/Languages/<locale>/server.lang, as
`key = value` lines. Keys get the file name as prefix in game
(`items.X.name` in server.lang is `server.items.X.name`).

Descriptions use a small markup:
  <color is="#ffffff">水</color>   coloured text
  <i>...</i>                        italics (the lore paragraph)
  <item is="Bench_Furnace"/>        the name of another item
  <msg key="server.items.K"/>       the text of another key
  \\n                               line break (written as backslash + n)
"""
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

def read_lang(source, locale):
    """All `key = value` pairs of <locale>/server.lang, keys prefixed with "server.".

    `source` is Assets.zip or a folder that holds Server/Languages (or the
    locale folders directly). Values keep the \\n escapes as written.
    """
    source = Path(source)
    if source.suffix == ".zip":
        with zipfile.ZipFile(source) as assets:
            text = assets.read(f"Server/Languages/{locale}/server.lang").decode("utf-8")
    else:
        candidates = [source / "Server" / "Languages" / locale / "server.lang", source / locale / "server.lang"]
        text = next(p for p in candidates if p.exists()).read_text(encoding="utf-8")
    return {"server." + k: v for k, v in parse_lang(text).items()}


def parse_lang(text):
    """Same rules as the game's LangFileParser: trimmed lines, # comments, a value
    ending in a backslash continues on the next line, "quotes" around a value
    are dropped, and the first definition of a key wins."""
    pairs, key, value = {}, None, ""
    for line in text.splitlines():
        line = line.strip()
        if key is None:
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if not k or not v:
                continue
            if v.endswith("\\"):
                key, value = k, v[:-1]
                continue
            if len(v) > 1 and v[0] == v[-1] == '"':
                v = v[1:-1]
            pairs.setdefault(k, v)
        elif line and not line.startswith("#"):
            more = line.endswith("\\")
            value += (line[:-1] if more else line).strip()
            if not more:
                pairs.setdefault(key, value)
                key, value = None, ""
    if key is not None:
        pairs.setdefault(key, value)
    return pairs


BREAK = "\u0001"  # marks where an item name starts and ends inside a text


def resolve_references(text, lang, depth=0):
    """Replace <item is="X"/> with X's name and <msg key="K"/> with K's text.

    Item names are wrapped in BREAK marks, so they are split into words on
    their own: 被<item is="Tool_Capture_Crate"/>所捕获 must not become 被捕 · 兽...
    """
    if depth > 5:  # a key that points at itself would loop forever
        return text
    text = re.sub(r'<item is="([^"]+)"/>',
                  lambda m: BREAK + lang.get(f"server.items.{m.group(1)}.name", m.group(1)) + BREAK, text)
    return re.sub(r'<msg key="([^"]+)"/>', lambda m: resolve_references(lang.get(m.group(1), ""), lang, depth + 1), text)


@dataclass
class Line:
    """One line of a description, as plain text plus each character's style."""
    text: str
    colors: list = field(default_factory=list)  # colour of each character, or None
    pieces: list = field(default_factory=list)  # the text cut at item names, to split into words separately
    italic: bool = False
    raw: str = ""  # the original markup, used as is when the line can't be parsed


def parse_line(markup, italic=False):
    """Split one line's markup into text + per-character colour.

    `italic` says whether an <i> is still open from an earlier line (some
    lore texts open it on one line and close it lines later). Returns the
    Line and whether <i> is still open after it. Only <color> and <i> are
    understood: a line with any other tag keeps its markup in `raw` and is
    shown as the game wrote it.
    """
    text, colors, color, any_italic = [], [], None, italic
    for token in re.split(r"(<[^>]+>)", markup):
        if not token:
            continue
        if token.startswith("<"):
            m = re.fullmatch(r'<color is="(#[0-9a-fA-F]{6})">', token)
            if m:
                color = m.group(1)
            elif token == "</color>":
                color = None
            elif token in ("<i>", "</i>"):
                italic = token == "<i>"
                any_italic |= italic
            else:
                return Line("", italic=False, raw=markup.replace(BREAK, "")), italic
            continue
        text.append(token)
        colors += [color] * len(token)
    joined = "".join(text)
    pieces = [p for p in joined.split(BREAK) if p]
    clean_colors = [c for ch, c in zip(joined, colors) if ch != BREAK]
    return Line(joined.replace(BREAK, ""), clean_colors, pieces=pieces, italic=any_italic), italic


def parse_description(description):
    """A description as paragraphs (split on \\n\\n) of parsed Lines (split on \\n)."""
    result, italic = [], False
    for paragraph in description.split("\\n\\n") if description else []:
        lines = []
        for markup in paragraph.split("\\n"):
            line, italic = parse_line(markup, italic)
            lines.append(line)
        result.append(lines)
    return result


def paragraphs(description):
    """A description's raw paragraphs, each a list of lines of markup (for the English text)."""
    return [p.split("\\n") for p in description.split("\\n\\n")] if description else []


@dataclass
class Item:
    id: str
    name_key: str
    description_key: str
    en_name: str
    zh_name: str | None
    en_description: str
    zh_description: str


def read_item_keys(path):
    """item-keys.tsv, written by the plugin at startup: id -> (name key, description key).

    Items usually use server.items.<ID>.name/.description, but an item can
    point at other keys and children inherit their parent's (the mithril
    hatchet shows the crude hatchet's description). Only the running game
    knows, so the plugin writes this file.
    """
    keys = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines()[1:]:
        if line.strip():
            item, name, description = line.split("\t")
            keys[item] = (name, description)
    return keys


def load_items(source, keys=None):
    """Every item with its keys, Chinese and English name, and both descriptions.

    Without `keys` (item-keys.tsv), every server.items.<ID>.name key is taken
    as an item using its default keys.
    """
    en, zh = read_lang(source, "en-US"), read_lang(source, "zh-CN")
    if keys is None:
        keys = {}
        for key in en:
            m = re.fullmatch(r"server\.items\.(.+)\.name", key)
            if m:
                keys[m.group(1)] = (key, f"server.items.{m.group(1)}.description")
    items = []
    for item, (name_key, desc_key) in sorted(keys.items()):
        if name_key not in en and name_key not in zh:
            continue  # internal items with no name at all
        items.append(Item(
            id=item,
            name_key=name_key,
            description_key=desc_key,
            en_name=en.get(name_key, item),
            zh_name=zh.get(name_key),
            en_description=resolve_references(en.get(desc_key, ""), en),
            zh_description=resolve_references(zh.get(desc_key, ""), zh),
        ))
    return items
