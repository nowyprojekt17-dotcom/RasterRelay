param(
  [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
  [string]$ComfyUrl = "http://127.0.0.1:8188",
  [int]$TimeoutSec = 900,
  [string]$PhotoshopPath = "C:\Program Files\Adobe\Adobe Photoshop (Beta)\Photoshop.exe",
  [string]$UxpDeveloperToolsPath = "C:\Program Files\Adobe\Adobe UXP Developer Tools\Adobe UXP Developer Tools.exe"
)

$ErrorActionPreference = "Stop"

function Wait-TcpPort {
  param(
    [string]$HostName,
    [int]$Port,
    [int]$TimeoutSec
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    $client = New-Object Net.Sockets.TcpClient
    try {
      $connect = $client.BeginConnect($HostName, $Port, $null, $null)
      if ($connect.AsyncWaitHandle.WaitOne(1000)) {
        $client.EndConnect($connect)
        return $true
      }
    } catch {
      Start-Sleep -Seconds 1
    } finally {
      $client.Close()
    }
  }

  return $false
}

function Test-Comfy {
  param([string]$Url)
  try {
    $response = Invoke-WebRequest -UseBasicParsing "$Url/system_stats" -TimeoutSec 5
    return $response.StatusCode -eq 200
  } catch {
    return $false
  }
}

function Start-AppIfNeeded {
  param(
    [string]$Path,
    [string]$ProcessName
  )

  $running = Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -ieq $ProcessName } |
    Select-Object -First 1

  if ($running) {
    return $running.Id
  }

  if (-not (Test-Path -LiteralPath $Path)) {
    throw "Missing executable: $Path"
  }

  $process = Start-Process -FilePath $Path -PassThru
  return $process.Id
}

function Find-NewestE2EReport {
  param([datetime]$Since)

  $roots = @(
    (Join-Path $env:APPDATA "Adobe"),
    (Join-Path $env:LOCALAPPDATA "Adobe")
  ) | Where-Object { Test-Path -LiteralPath $_ }

  foreach ($root in $roots) {
    $match = Get-ChildItem -LiteralPath $root -Recurse -Filter "rasterrelay-e2e-*-summary.json" -ErrorAction SilentlyContinue |
      Where-Object { $_.LastWriteTime -ge $Since } |
      Sort-Object LastWriteTime -Descending |
      Select-Object -First 1

    if ($match) {
      return $match.FullName
    }
  }

  return $null
}

$startedAt = Get-Date
$pluginRoot = Join-Path $RepoRoot "photoshop_plugin"
$manifestPath = Join-Path $pluginRoot "manifest.json"
$flagPath = Join-Path $pluginRoot "e2e-autostart.flag"
$loaderScript = Join-Path $RepoRoot "scripts\load-uxp-plugin.mjs"

if (-not (Test-Path -LiteralPath $manifestPath)) {
  throw "Missing RasterRelay manifest: $manifestPath"
}

if (-not (Test-Comfy -Url $ComfyUrl)) {
  throw "ComfyUI is not responding at $ComfyUrl. Start RasterRelay Launcher / ComfyUI first."
}

Set-Content -LiteralPath $flagPath -Value "run-on-next-panel-load" -Encoding UTF8
Write-Host "E2E autostart flag written: $flagPath"

$photoshopPid = Start-AppIfNeeded -Path $PhotoshopPath -ProcessName "Photoshop"
Write-Host "Photoshop PID: $photoshopPid"

$uxpPid = Start-AppIfNeeded -Path $UxpDeveloperToolsPath -ProcessName "Adobe UXP Developer Tools"
Write-Host "UXP Developer Tools PID: $uxpPid"

if (-not (Wait-TcpPort -HostName "127.0.0.1" -Port 14001 -TimeoutSec 90)) {
  throw "Adobe UXP Developer Tools CLI did not open on 127.0.0.1:14001."
}

node $loaderScript $pluginRoot
if ($LASTEXITCODE -ne 0) {
  throw "UXP plugin load failed with exit code $LASTEXITCODE."
}

$deadline = (Get-Date).AddSeconds($TimeoutSec)
do {
  $reportPath = Find-NewestE2EReport -Since $startedAt
  if ($reportPath) {
    $report = Get-Content -Raw -LiteralPath $reportPath | ConvertFrom-Json
    $audit = $report.compositeAudit
    if (-not $report.ok) {
      throw "RasterRelay E2E report is not OK: $reportPath"
    }
    if (-not $audit.passed) {
      throw "RasterRelay E2E audit failed: $($audit | ConvertTo-Json -Compress)"
    }
    if ($audit.outsideChangedPixels -ne 0 -or $audit.maxDiffOutsideAlphaBBox -ne 0) {
      throw "RasterRelay E2E outside-alpha invariant failed: $($audit | ConvertTo-Json -Compress)"
    }
    if ($audit.sourceHueCheckedPixels -gt 0 -and $audit.sourceHueMaxErrorInsideChanged -gt 1.5) {
      throw "RasterRelay E2E source-hue invariant failed: $($audit | ConvertTo-Json -Compress)"
    }
    if ($audit.sourceChromaMaxErrorInsideChanged -gt 1) {
      throw "RasterRelay E2E source RGB-chroma invariant failed: $($audit | ConvertTo-Json -Compress)"
    }

    Write-Host "RasterRelay Photoshop E2E OK:"
    Write-Host $reportPath
    Write-Host ($audit | ConvertTo-Json -Compress)
    exit 0
  }

  Start-Sleep -Seconds 3
} while ((Get-Date) -lt $deadline)

throw "Timed out waiting for RasterRelay E2E summary JSON."
