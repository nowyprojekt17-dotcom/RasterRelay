<#
.SYNOPSIS
  One-shot reload of the RasterRelay ComfyUI nodes: reinstall (copy repo ->
  custom_nodes), restart ComfyUI, wait until it answers.

.DESCRIPTION
  The nodes are installed as a COPY (not a symlink), so any change in the repo
  needs a reinstall + ComfyUI restart to take effect. This script does both,
  matching the python auto-detection described in the README (venv / portable /
  system). Use it after editing anything under comfy_nodes/.

.EXAMPLE
  .\scripts\reload-rasterrelay-nodes.ps1
  .\scripts\reload-rasterrelay-nodes.ps1 -ComfyRoot "E:\AI\ComfyUI" -Port 8188
#>
param(
    [string]$ComfyRoot = "E:\AI\ComfyUI",
    [int]$Port = 8188,
    [int]$ReadyTimeoutSec = 180,
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Write-Step([string]$m) { Write-Host "[reload] $m" -ForegroundColor Cyan }

# 1. Reinstall nodes
Write-Step "Reinstaluje wezly RasterRelay -> $ComfyRoot\custom_nodes\rasterrelay_nodes"
& (Join-Path $PSScriptRoot "install-comfy-nodes.ps1") -ComfyRoot $ComfyRoot | Out-Null

if ($NoRestart) {
    Write-Step "Pomijam restart (-NoRestart). Zrestartuj ComfyUI recznie, by zaladowac zmiany."
    return
}

# 2. Find python the way the README describes: venv -> venv -> portable -> system
function Resolve-ComfyPython([string]$root) {
    $candidates = @(
        (Join-Path $root ".venv\Scripts\python.exe"),
        (Join-Path $root "venv\Scripts\python.exe"),
        (Join-Path (Split-Path -Parent $root) "python_embeded\python.exe"),
        (Join-Path $root "python_embeded\python.exe")
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    $sys = (Get-Command python -ErrorAction SilentlyContinue)
    if ($sys) { return $sys.Source }
    throw "Nie znalazlem Pythona dla ComfyUI w $root (sprawdzono venv/.venv/portable/system)."
}

$python = Resolve-ComfyPython $ComfyRoot
$mainPy = Join-Path $ComfyRoot "main.py"
if (-not (Test-Path $mainPy)) { throw "Brak main.py w $ComfyRoot - to nie jest folder ComfyUI." }

# 3. Stop any ComfyUI listening on the port
$conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) {
    Write-Step "Zatrzymuje ComfyUI na porcie $Port (PID $($conn.OwningProcess))"
    Stop-Process -Id $conn.OwningProcess -Force
    Start-Sleep -Seconds 2
} else {
    Write-Step "Brak dzialajacego ComfyUI na porcie $Port - uruchamiam nowe."
}

# 4. Relaunch ComfyUI detached
$log = Join-Path $repoRoot "comfyui-startup.log"
Write-Step "Startuje ComfyUI: $python main.py --listen 127.0.0.1 --port $Port"
$proc = Start-Process -FilePath $python `
    -ArgumentList @("main.py", "--listen", "127.0.0.1", "--port", "$Port") `
    -WorkingDirectory $ComfyRoot `
    -RedirectStandardOutput $log -RedirectStandardError "$log.err" `
    -PassThru -WindowStyle Hidden
Write-Step "ComfyUI PID $($proc.Id), log: $log"

# 5. Wait until it answers
$deadline = (Get-Date).AddSeconds($ReadyTimeoutSec)
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/system_stats" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) {
            Write-Step "ComfyUI gotowe na http://127.0.0.1:$Port"
            # confirm RasterRelay nodes loaded
            try {
                $info = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/object_info/RasterRelaySeamlessTone" -UseBasicParsing -TimeoutSec 3
                if ($info.StatusCode -eq 200) { Write-Step "Wezly RasterRelay zaladowane (SeamlessTone OK)." }
            } catch { Write-Host "[reload] UWAGA: nie potwierdzono zaladowania wezlow RasterRelay." -ForegroundColor Yellow }
            return
        }
    } catch { Start-Sleep -Seconds 3 }
}
Write-Host "[reload] UWAGA: ComfyUI nie odpowiedzialo w $ReadyTimeoutSec s. Sprawdz log: $log" -ForegroundColor Yellow
