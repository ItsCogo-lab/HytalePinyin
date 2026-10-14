# HytalePinyin client patch: installs the fonts with every pinyin letter and
# the menus with pinyin into the Hytale client, keeping a backup of the
# originals. The HytalePinyin mod (the .jar) does the rest from the server.
#
#   Right click > Run with PowerShell, or:
#   powershell -ExecutionPolicy Bypass -File install.ps1            # install
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Restore   # put the originals back
#
# Close Hytale first: the game locks some of these files while it runs.
# Game updates overwrite them: run it again after each update.
param([switch]$Restore)
$ErrorActionPreference = 'Stop'

$shared = Join-Path $env:APPDATA 'Hytale\install\release\package\game\latest\Client\Data\Shared'
$fonts  = Join-Path $shared 'UI\Fonts'
$backup = Join-Path $fonts '_hytalepinyin_backup'

# Each file: where it goes in the game (from Client\Data\Shared) -> where it
# is in this folder. The backup keeps the game's path without "UI\Fonts\".
$files = @{}
foreach ($name in 'NunitoSans-Medium', 'NunitoSans-ExtraBold', 'NotoSans-Bold') {
    foreach ($ext in 'json', 'png') { $files["UI\Fonts\$name.$ext"] = "Fonts\$name.$ext" }
}
# The Chinese font is split into pages; only the last one carries the pinyin letters
$files['UI\Fonts\NotoSansSC-Medium\NotoSansSC-Medium_71.json'] = 'Fonts\NotoSansSC-Medium\NotoSansSC-Medium_71.json'
$files['UI\Fonts\NotoSansSC-Medium\NotoSansSC-Medium_71.png']  = 'Fonts\NotoSansSC-Medium\NotoSansSC-Medium_71.png'
# The main menu and other screens read the .ttf itself
$files['UI\Fonts\NotoSansSC-Medium.ttf'] = 'Fonts\NotoSansSC-Medium.ttf'
# Menu texts with pinyin
$files['Language\zh-CN\client.lang'] = 'Language\zh-CN\client.lang'

if (-not (Test-Path $shared)) { throw "Hytale not found: $shared" }
if (Get-Process -Name 'HytaleClient' -ErrorAction SilentlyContinue) { throw 'Close Hytale first, then run this again.' }

# Earlier versions of the mod (named VividHanzi) kept the originals here
$oldBackup = Join-Path $fonts '_vividhanzi_backup'
if ((Test-Path $oldBackup) -and -not (Test-Path $backup)) { Rename-Item $oldBackup '_hytalepinyin_backup' }

if ($Restore) {
    foreach ($game in $files.Keys) {
        $bak = Join-Path $backup ($game -replace '^UI\\Fonts\\', '')
        if (Test-Path $bak) { Copy-Item $bak (Join-Path $shared $game) -Force }
    }
    Write-Host 'Original files restored.'
    exit
}

# Back up the game's file unless it is already ours (a second install must
# not overwrite the real originals with our copies). After a game update the
# game's files are original again, so they get backed up again.
foreach ($game in $files.Keys) {
    $orig = Join-Path $shared $game
    $ours = Join-Path $PSScriptRoot $files[$game]
    $bak  = Join-Path $backup ($game -replace '^UI\\Fonts\\', '')
    New-Item -ItemType Directory -Force (Split-Path $bak) | Out-Null
    $isOurs = (Test-Path $orig) -and ((Get-FileHash $orig).Hash -eq (Get-FileHash $ours).Hash)
    if ((Test-Path $orig) -and -not $isOurs) { Copy-Item $orig $bak -Force }
    Copy-Item $ours $orig -Force
}
Write-Host 'HytalePinyin client patch installed. Start Hytale with the game language set to Simplified Chinese.'
