# Glossary

Builds every item's Chinese name, pinyin and description from the game's own
texts. Nothing is translated by hand: the Chinese and English are Hytale's
official texts, and the readings come from VividHanzi's pinyin pipeline
(CC-CEDICT + pinyin-pro), the same one the VividHanzi app uses.

```
python3 glossary/build.py --game "<Hytale>/install/release/package/game/latest" \
    --item-keys "<Hytale>/UserData/Saves/<world>/mods/<plugin folder>/item-keys.tsv" \
    --vividhanzi ../VividHanzi --hanzidict ../HanziDict/v1
```

`item-keys.tsv` is written by the plugin each time a world starts. It says
which name and description keys each item really uses: items can point at
other items' keys and inherit their parent's (the mithril hatchet shows the
crude hatchet's description). A description shared by several items gets
no name header, since it can't know which item is showing it.

Needs Python 3.10+ with `fontTools` and `wordfreq`, Node 22+, a VividHanzi checkout (with
`npm ci` done and `scripts/hytale/export.ts`) and a HanziDict checkout.

## Files you edit

| File | What it is |
| --- | --- |
| `game-terms.tsv` | Words the dictionary doesn't have, or that must stay together (`铁栏杆`). Used when splitting texts into words. |
| `fixes.tsv` | The right reading for a word the pipeline wasn't sure of. Only used where it is unsure, so a fix for 长 never touches 成长. |

After each run, `out/review.tsv` lists the readings still unsure. Add each
one to `fixes.tsv` (or a longer word to `game-terms.tsv`) and run again
until it is empty.

## Output (`out/`)

| File | What it is |
| --- | --- |
| `glossary.tsv` | One row per item: ID, English, Chinese, pinyin, words with their pinyin, flags. |
| `review.tsv` | Readings to check, most frequent first. |
| `items.json` | Each item's annotated name and description, for the plugin. |
| `breakdown.json` | Dictionary entries for every word and character used, plus HSK 1-4. |
| `lang/zh-CN.lang` | Tooltip texts: `汉字 (pinyin)` title, tone-coloured pinyin, pinyin above the description. |
| `lang/zh-CN.english.lang` | The same plus the official English name and description in grey (`/hanzi`). |
