"""Pinyin for the game's menus and other short labels (制作, 物品栏, 等级 {level}).

Two sources:
  - Server/Languages/zh-CN/server.lang: bench categories, resource types,
    NPC names... The plugin replaces them like the item texts.
  - Client/Data/Shared/Language/zh-CN/client.lang: buttons, inventory, HUD,
    settings. The client reads this file itself, so a server plugin can't
    change it: the installer replaces the game's copy (keeping a backup).

Only short labels get pinyin: sentences would not fit in a button. The
pinyin goes after the label in the small letters (see small_pinyin.py), in
brackets: "制作 (zhìzuò)". A label with placeholders gets it after each
Chinese part, so it stays next to its words: "按 (àn) {key} 收获 (shōuhuò) {item}". Being Private Use characters, the small letters
are also safe from menus that write everything in capitals.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from small_pinyin import small  # noqa: E402

MAX_HANZI = 8  # longer texts are sentences, not labels
SENTENCE = re.compile(r"[。，；！？：、]")
HAN = re.compile(r"[㐀-鿿]")

# server.lang groups whose short texts are labels players see. Left out:
# commands (chat replies), builder and asset editor tools, internal names.
SERVER_GROUPS = {"benchCategories", "resourceType", "npcRoles", "ui", "general", "map", "hud",
                 "interactionHints", "portals", "objectives", "barter", "memories", "worldevent",
                 "customUI", "npc", "interactions"}
# client.lang groups left out: developer and creative tools nobody needs pinyin in.
CLIENT_SKIP = {"builderTools", "assetEditor", "profiling", "machinima", "devTools"}


def is_label(value):
    """A short text with Chinese, no sentence punctuation and no markup or plural rules."""
    han = len(HAN.findall(value))
    return 1 <= han <= MAX_HANZI and not SENTENCE.search(value) and "<" not in value \
        and not re.search(r"\{[^}]*,", value) and "(" not in value and "（" not in value


def server_labels(zh):
    """server.lang keys (prefixed "server.") that get pinyin, key -> text."""
    return {k: v for k, v in zh.items()
            if not k.startswith("server.items.") and k.split(".")[1] in SERVER_GROUPS and is_label(v)}


def client_labels(client):
    """client.lang keys that get pinyin, key -> text."""
    return {k: v for k, v in client.items() if k.split(".")[0] not in CLIENT_SKIP and is_label(v)}


def with_pinyin(text, pinyin):
    """'制作' + 'zhìzuò' -> '制作 (zhìzuò)' with the pinyin in small letters."""
    return f"{text} ({small(pinyin)})" if pinyin else text


PLACEHOLDER = re.compile(r"(\{[^}]*\})")


def chinese_parts(text):
    """The pieces of a label that get their own pinyin: the text between
    placeholders, up to its last Chinese character ('收获' in '按 {key} 收获{item}')."""
    parts = []
    for part in PLACEHOLDER.split(text):
        last = max((i for i, c in enumerate(part) if HAN.match(c)), default=-1)
        if last >= 0 and not PLACEHOLDER.fullmatch(part):
            parts.append(part[:last + 1].strip())
    return parts


def label_with_pinyin(text, pinyin_of):
    """The label with each Chinese part followed by its pinyin; `pinyin_of`
    gives the pinyin of one part (see chinese_parts)."""
    out, parts = "", PLACEHOLDER.split(text)
    for n, part in enumerate(parts):
        last = max((i for i, c in enumerate(part) if HAN.match(c)), default=-1)
        if last < 0 or PLACEHOLDER.fullmatch(part):
            out += part
            continue
        head, tail = part[:last + 1], part[last + 1:]
        lead = head[:len(head) - len(head.lstrip())]
        labelled = lead + with_pinyin(head.strip(), pinyin_of(head.strip()))
        # keep a space between the pinyin and a placeholder that follows it
        out += labelled + (tail if tail or n == len(parts) - 1 else " ")
    return out


def patch_lang_file(original, replacements):
    """The original .lang text with some single-line values replaced, everything
    else (comments, order, multi-line values) left exactly as it was."""
    out = []
    for line in original.splitlines():
        m = re.match(r"^(\s*)([^#=\s][^=]*?)(\s*=\s*)(.*)$", line)
        if m and m.group(2) in replacements and not m.group(4).endswith("\\"):
            line = m.group(1) + m.group(2) + m.group(3) + replacements[m.group(2)]
        out.append(line)
    return "\n".join(out) + "\n"
