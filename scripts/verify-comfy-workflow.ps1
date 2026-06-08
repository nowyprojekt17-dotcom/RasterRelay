param(
    [string]$ComfyUrl = "http://127.0.0.1:8188",
    [string]$ComfyRoot = "E:\AI\ComfyUI",
    [int]$Steps = 1
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[RasterRelay] $Message"
}

function Read-JsonFile {
    param([string]$Path)
    Get-Content -Path $Path -Raw | ConvertFrom-Json
}

function Assert-PngHasAlpha {
    param(
        [string]$Path,
        [int]$CropLeft = 0,
        [int]$CropTop = 0,
        [int]$CropSize = 0
    )

    Add-Type -AssemblyName System.Drawing
    $image = [System.Drawing.Bitmap]::FromFile($Path)
    try {
        $format = $image.PixelFormat
        $hasAlpha = $format -eq "Format32bppArgb" -or $format -eq "Format64bppArgb"
        if (-not $hasAlpha) {
            throw "Wynik ($format) nie ma kanału alfa. RasterRelaySaveImage powinien zapisywac PNG RGBA."
        }

        $w = $image.Width
        $h = $image.Height

        $checkPoints = @()

        if ($CropSize -gt 0 -and $CropSize -lt $w -and $CropSize -lt $h) {
            $rightAfterCrop = [Math]::Min($CropLeft + $CropSize + 30, $w - 1)
            $bottomAfterCrop = [Math]::Min($CropTop + $CropSize + 30, $h - 1)
            $checkPoints += @{ x = $rightAfterCrop; y = $CropTop + 10; label = "po prawej cropu" }
            $checkPoints += @{ x = $CropLeft + 10; y = $bottomAfterCrop; label = "pod cropem" }
        } else {
            $checkPoints += @{ x = $w - 2; y = 1; label = "prawy gorny" }
            $checkPoints += @{ x = 1; y = $h - 2; label = "lewy dolny" }
        }

        foreach ($c in $checkPoints) {
            $pixel = $image.GetPixel($c.x, $c.y)
            if ($pixel.A -gt 8) {
                throw "Punkt $($c.label) ($($c.x),$($c.y)) ma alpha=$($pixel.A). RasterRelayPadToDocument powinien zostawic przezroczystosc poza cropem."
            }
        }
    } finally {
        $image.Dispose()
    }
}

function ConvertTo-Hashtable {
    param([Parameter(ValueFromPipeline)]$InputObject)

    if ($null -eq $InputObject) {
        return $null
    }

    if ($InputObject -is [System.Collections.IEnumerable] -and $InputObject -isnot [string] -and $InputObject -isnot [pscustomobject]) {
        $items = @()
        foreach ($item in $InputObject) {
            $items += ConvertTo-Hashtable $item
        }
        return $items
    }

    if ($InputObject -is [pscustomobject]) {
        $hash = [ordered]@{}
        foreach ($property in $InputObject.PSObject.Properties) {
            $hash[$property.Name] = ConvertTo-Hashtable $property.Value
        }
        return $hash
    }

    return $InputObject
}

function New-TestImages {
    param([string]$InputDir)

    Add-Type -AssemblyName System.Drawing

    if (-not (Test-Path -Path $InputDir)) {
        New-Item -ItemType Directory -Path $InputDir -Force | Out-Null
    }

    $sourcePath = Join-Path $InputDir "rasterrelay-api-test-source.png"
    $maskPath = Join-Path $InputDir "rasterrelay-api-test-mask.png"

    $source = New-Object System.Drawing.Bitmap 256, 256
    $graphics = [System.Drawing.Graphics]::FromImage($source)
    $graphics.Clear([System.Drawing.Color]::FromArgb(238, 238, 238))
    $blueBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(42, 111, 219))
    $graphics.FillRectangle($blueBrush, 48, 48, 160, 160)
    $graphics.Dispose()
    $source.Save($sourcePath, [System.Drawing.Imaging.ImageFormat]::Png)
    $source.Dispose()

    $mask = New-Object System.Drawing.Bitmap 256, 256
    $maskGraphics = [System.Drawing.Graphics]::FromImage($mask)
    $maskGraphics.Clear([System.Drawing.Color]::Black)
    $whiteBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::White)
    $maskGraphics.FillEllipse($whiteBrush, 64, 64, 128, 128)
    $maskGraphics.Dispose()
    $mask.Save($maskPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $mask.Dispose()

    return @{
        SourceName = "rasterrelay-api-test-source.png"
        MaskName = "rasterrelay-api-test-mask.png"
        SourcePath = $sourcePath
        MaskPath = $maskPath
    }
}

function Assert-WorkflowClassesExist {
    param(
        [hashtable]$Workflow,
        [object]$ObjectInfo
    )

    $available = @{}
    foreach ($property in $ObjectInfo.PSObject.Properties) {
        $available[$property.Name] = $true
    }

    $missing = @()
    foreach ($nodeId in $Workflow.Keys) {
        $classType = $Workflow[$nodeId].class_type
        if (-not $available.ContainsKey($classType)) {
            $missing += "${nodeId}:${classType}"
        }
    }

    if ($missing.Count -gt 0) {
        throw "ComfyUI nie ma wymaganych node'ow: $($missing -join ', ')"
    }
}

function Wait-ForPromptResult {
    param(
        [string]$PromptId,
        [string]$ComfyUrl,
        [int]$TimeoutSeconds = 300
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    do {
        $history = Invoke-RestMethod -Uri "$ComfyUrl/history/$PromptId" -TimeoutSec 20
        if ($history.PSObject.Properties.Name -contains $PromptId) {
            return $history.$PromptId
        }

        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)

    throw "ComfyUI nie zwrocilo wyniku w ciagu $TimeoutSeconds sekund."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$workflowPath = Join-Path $repoRoot "photoshop_plugin\workflows\inpainting-api.json"
$mappingPath = Join-Path $repoRoot "photoshop_plugin\workflows\inpainting-api.mapping.json"
$inputDir = Join-Path $ComfyRoot "input"
$outputDir = Join-Path $ComfyRoot "output"

Write-Step "Sprawdzam ComfyUI: $ComfyUrl"
$systemStats = Invoke-RestMethod -Uri "$ComfyUrl/system_stats" -TimeoutSec 10
Write-Step "ComfyUI odpowiada. Wersja: $($systemStats.system.comfyui_version)"

Write-Step "Czytam workflow API."
$workflow = ConvertTo-Hashtable (Read-JsonFile $workflowPath)
$mapping = Read-JsonFile $mappingPath

if ($mapping.status -ne "ready") {
    throw "Mapping workflow nie ma statusu ready."
}

Write-Step "Sprawdzam, czy lokalne ComfyUI zna wszystkie node'y workflow."
$objectInfo = Invoke-RestMethod -Uri "$ComfyUrl/object_info" -TimeoutSec 20
Assert-WorkflowClassesExist -Workflow $workflow -ObjectInfo $objectInfo

Write-Step "Tworze maly obraz i maske testowa w folderze input ComfyUI."
$testImages = New-TestImages -InputDir $inputDir

$workflow["10"].inputs.image = $testImages.SourceName
$workflow["11"].inputs.image = $testImages.MaskName
$workflow["31"].inputs.text = "replace the blue square with a red circular patch, preserve the gray background"
$workflow["62"].inputs.steps = $Steps
$workflow["80"].inputs.filename_prefix = "RasterRelay/api-test"

$payload = @{
    client_id = "rasterrelay-api-test"
    prompt = $workflow
}

Write-Step "Wysylam workflow do /prompt. Kroki: $Steps"
$response = Invoke-RestMethod -Uri "$ComfyUrl/prompt" -Method Post -ContentType "application/json" -Body ($payload | ConvertTo-Json -Depth 100) -TimeoutSec 30

if ($response.node_errors -and $response.node_errors.PSObject.Properties.Count -gt 0) {
    throw "ComfyUI zwrocilo node_errors: $($response.node_errors | ConvertTo-Json -Depth 20)"
}

Write-Step "Prompt ID: $($response.prompt_id). Czekam na wynik."
$historyEntry = Wait-ForPromptResult -PromptId $response.prompt_id -ComfyUrl $ComfyUrl

if ($historyEntry.status.status_str -ne "success") {
    throw "Workflow nie zakonczyl sie sukcesem: $($historyEntry.status | ConvertTo-Json -Depth 20)"
}

$firstImage = $null
foreach ($outputProperty in $historyEntry.outputs.PSObject.Properties) {
    $images = $outputProperty.Value.images
    if ($images -and $images.Count -gt 0) {
        $firstImage = $images[0]
        break
    }
}

if (-not $firstImage) {
    throw "Workflow zakonczyl sie, ale nie znaleziono obrazu wyjsciowego."
}

$resultPath = Join-Path (Join-Path $outputDir $firstImage.subfolder) $firstImage.filename

Write-Step "Weryfikuję kanał alfa w pliku wynikowym."
Assert-PngHasAlpha -Path $resultPath -CropLeft $workflow["91"].inputs.crop_left -CropTop $workflow["91"].inputs.crop_top -CropSize 256

Write-Step "SUKCES. Wynik testowy: $resultPath"
Write-Step "Ten test sprawdza ComfyUI i workflow. Ostatni etap nadal wymaga Photoshopa Beta 27.8."
