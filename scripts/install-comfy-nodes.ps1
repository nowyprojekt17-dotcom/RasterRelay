param(
    [string]$ComfyRoot = "E:\AI\ComfyUI"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$sourceDir = Join-Path $repoRoot "comfy_nodes"
$targetDir = Join-Path $ComfyRoot "custom_nodes\rasterrelay_nodes"

function Write-Step {
    param([string]$Message)
    Write-Host "[RasterRelay] $Message"
}

if (-not (Test-Path -Path $ComfyRoot)) {
    throw "Nie znaleziono folderu ComfyUI: $ComfyRoot. Uzyj parametru -ComfyRoot."
}

if (-not (Test-Path -Path (Join-Path $ComfyRoot "main.py"))) {
    throw "Folder $ComfyRoot nie zawiera pliku main.py. To nie jest poprawna instalacja ComfyUI."
}

Write-Step "Usuwam stara instalacje: $targetDir"
if (Test-Path -Path $targetDir) {
    Remove-Item -Path $targetDir -Recurse -Force
}

Write-Step "Kopiuje custom nodes z $sourceDir do $targetDir"
New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
Copy-Item -Path (Join-Path $sourceDir "*") -Destination $targetDir -Recurse -Force

Write-Step "Instalacja gotowa. Zrestartuj ComfyUI zeby zaladowal nowe wezly."
Write-Step "Custom nodes RasterRelay:"
Get-ChildItem -Path (Join-Path $targetDir "nodes") -Filter "*.py" | ForEach-Object {
    Write-Host "  - $($_.BaseName)"
}
