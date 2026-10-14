HytalePinyin client patch
=========================

The HytalePinyin mod (HytalePinyin.jar) puts pinyin in item names,
descriptions and in-game labels. Two things it can't do from the server:

  - fonts: Hytale's fonts lack some pinyin letters (ǐ ǒ ǚ ǜ ...) and the
    small letters the mod uses above Chinese text; without this patch they
    show as "?" or boxes.
  - menus: the main menu, settings and other client screens get pinyin
    from a patched zh-CN/client.lang.

Install (Windows):
  1. Close Hytale.
  2. Right click install.ps1 > Run with PowerShell.
  3. Start Hytale with the language set to 简体中文 (Simplified Chinese).

The originals are kept in ...\Client\Data\Shared\UI\Fonts\_hytalepinyin_backup.
Undo:  powershell -ExecutionPolicy Bypass -File install.ps1 -Restore
Game updates replace these files: run install.ps1 again after an update.

Built for Hytale 0.7.1. The menu texts are the game's official Chinese texts
with pinyin added; after a game update with new menus, use the patch version
made for it.
