**Learn Chinese while you play.** HytalePinyin adds tone-marked pinyin to Hytale's own Simplified Chinese texts, so every item, description and menu becomes reading practice.

## What it does

![image](https://media.forgecdn.net/attachments/description/null/description_1ecea76c-5c76-48c8-b535-c3202309aa8d.png)

- **Item names** with pinyin: 铁手斧 (tiě shǒu fǔ)
- **Descriptions** with pinyin above every word, lined up with the characters
- **Labels and menus**: benches, rarities, interaction hints (按 (àn) [F] 收获 (shōuhuò) …), the main menu, settings and the loading screen
- **`/hanzi colors`**: colour the pinyin by tone (off by default)
- **`/hanzi english`**: show the official English name and description next to the Chinese (off by default)
- Settings are per player and remembered

![image](https://media.forgecdn.net/attachments/description/null/description_a44da6c2-a966-4e65-b6b7-630706604227.png)

MENU_SCREENSHOT_HERE

All texts are Hytale's official translations: nothing is machine-translated. Readings come from CC-CEDICT and pinyin-pro, with 一/不 tone changes and words split by frequency.

## Install

1. Install the mod from CurseForge, or put **HytalePinyin-v0.1.0-Hytale-0.7.1.jar** in `%APPDATA%\Hytale\UserData\Mods`, and enable it in your world's mod list.
2. Set the game language to **简体中文** (Simplified Chinese).
3. Open a singleplayer world. The mod adds the pinyin letters Hytale's fonts are missing and the menus with pinyin to your game, and tells you in chat to **restart Hytale once**. After that, everything shows pinyin.

It keeps a copy of every game file it changes (in `Client\Data\Shared\UI\Fonts\_hytalepinyin_backup`). `/hanzi restore` puts Hytale's originals back (restart Hytale afterwards) and `/hanzi install` brings the pinyin back. After a game update, the next world you open installs it again.

**Playing on a server?** The server can't reach your computer: install the mod yourself, open any singleplayer world with it once and restart Hytale. The mod tells you in chat if your pinyin shows as boxes.

## Notes

- Made for Hytale 0.7.1, Windows.
- Only players with the game in Simplified Chinese see the pinyin; everyone else keeps their language.
- Fan-made, not affiliated with Hypixel Studios. Code under MIT; pinyin data under CC BY-SA 4.0 (CC-CEDICT); fonts under the SIL Open Font License. See NOTICE.md inside the jar.
