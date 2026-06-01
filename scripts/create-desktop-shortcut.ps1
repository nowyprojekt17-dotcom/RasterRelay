param(
    [string] $ShortcutName = "RasterRelay Launcher"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$launcherExe = Join-Path $repoRoot "launcher\src-tauri\target\release\rasterrelay-launcher.exe"

if (-not (Test-Path -LiteralPath $launcherExe)) {
    throw "Nie znaleziono Launchera: $launcherExe. Najpierw uruchom: npm run tauri -- build --debug w folderze launcher."
}

$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "$ShortcutName.lnk"
$iconPath = Join-Path $repoRoot "launcher\src-tauri\icons\icon.ico"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcherExe
$shortcut.WorkingDirectory = Split-Path -Parent $launcherExe
$shortcut.Description = "RasterRelay Launcher"

if (Test-Path -LiteralPath $iconPath) {
    $shortcut.IconLocation = $iconPath
}

$shortcut.Save()

Write-Host "Utworzono skrót: $shortcutPath"
