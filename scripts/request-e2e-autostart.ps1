$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$flagPath = Join-Path $repoRoot "photoshop_plugin\e2e-autostart.flag"

Set-Content -LiteralPath $flagPath -Value "run-on-next-panel-load" -Encoding UTF8
Write-Host "RasterRelay E2E autostart flag written:"
Write-Host $flagPath
