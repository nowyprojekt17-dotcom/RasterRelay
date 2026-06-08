# Practical inpainting test: real photo, meaningful mask, production settings.
# - Resizes a real test image to 1024x768 (model-safe multiple of 16)
# - Defines a 512x320 region to inpaint in the center
# - Builds a full-document mask (inpaint region = white, rest = black)
# - Exports a cropped source PNG (the inpaint region) for the workflow's LoadImage
# - Sends the workflow with cfg=1, 14 steps, realistic prompt
# - Polls /history, downloads the padded output
# - Verifies alpha channel via Bitmap inspection

param(
    [string]$ComfyUrl = "http://127.0.0.1:8188",
    [string]$ComfyRoot = "E:\AI\ComfyUI",
    [string]$SourceImage = "C:\Users\Mierz\Desktop\RasterRelay\Testy\Obrazy do testowania\envato-labs-ai-da532839-090d-4b70-9e60-1ed61c2e94a5.jpg",
    [string]$Prompt = "a wooden cutting board with a fresh loaf of bread and a knife, warm kitchen lighting, photorealistic, soft shadows",
    [int]$Steps = 14,
    [string]$OutputSubdir = "RasterRelay/practical-test"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

function Write-Step($msg) { Write-Host "[PracticalTest] $msg" }
function Get-ComfyStats { Invoke-RestMethod -Uri "$ComfyUrl/system_stats" -TimeoutSec 10 }
function Get-ComfyObjectInfo { Invoke-RestMethod -Uri "$ComfyUrl/object_info" -TimeoutSec 20 }

function ConvertTo-Hashtable {
    param([Parameter(ValueFromPipeline)]$InputObject)

    if ($null -eq $InputObject) { return $null }

    if ($InputObject -is [System.Collections.IEnumerable] -and $InputObject -isnot [string] -and $InputObject -isnot [pscustomobject]) {
        $items = @()
        foreach ($item in $InputObject) { $items += ConvertTo-Hashtable $item }
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

# --- Step 1: prepare a model-safe source image ---
$repoRoot = "C:\Users\Mierz\Desktop\RasterRelay"
$workflowPath = Join-Path $repoRoot "photoshop_plugin\workflows\inpainting-api.json"
$mappingPath = Join-Path $repoRoot "photoshop_plugin\workflows\inpainting-api.mapping.json"
$inputDir = Join-Path $ComfyRoot "input"
$outputDir = Join-Path $ComfyRoot "output"
if (-not (Test-Path $inputDir)) { New-Item -ItemType Directory -Path $inputDir -Force | Out-Null }

$docW = 1024
$docH = 768
$cropL = 256
$cropT = 224
$cropW = 512
$cropH = 320

Write-Step "Resize source image -> $docW x $docH"
$docBmp = New-Object System.Drawing.Bitmap $docW, $docH
$g = [System.Drawing.Graphics]::FromImage($docBmp)
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
$g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
$src = [System.Drawing.Image]::FromFile($SourceImage)
$g.DrawImage($src, 0, 0, $docW, $docH)
$g.Dispose()
$src.Dispose()

# --- Step 2: export cropped source (what the workflow will edit) ---
$croppedBmp = New-Object System.Drawing.Bitmap $cropW, $cropH
$cg = [System.Drawing.Graphics]::FromImage($croppedBmp)
$cg.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$cg.DrawImage($docBmp, [System.Drawing.Rectangle]::FromLTRB(0, 0, $cropW, $cropH), [System.Drawing.Rectangle]::FromLTRB($cropL, $cropT, $cropL + $cropW, $cropT + $cropH), [System.Drawing.GraphicsUnit]::Pixel)
$cg.Dispose()

$sourceName = "practical-test-source.png"
$sourcePath = Join-Path $inputDir $sourceName
$croppedBmp.Save($sourcePath, [System.Drawing.Imaging.ImageFormat]::Png)
$croppedBmp.Dispose()
Write-Step "Cropped source saved: $sourcePath ($cropW x $cropH)"

# --- Step 3: build full-document mask (inpaint region = white, rest = black) ---
# Make the inpaint region a rounded rectangle so the test is more realistic than a hard square.
$maskBmp = New-Object System.Drawing.Bitmap $docW, $docH
$mg = [System.Drawing.Graphics]::FromImage($maskBmp)
$mg.Clear([System.Drawing.Color]::Black)
$whiteBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::White)
$mg.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$mg.FillRectangle($whiteBrush, $cropL, $cropT, $cropW, $cropH)
# Add a soft edge by overlaying a Gaussian-like falloff via a second pass with reduced alpha
$softBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(96, 255, 255, 255))
$mg.FillRectangle($softBrush, $cropL - 8, $cropT - 8, $cropW + 16, $cropH + 16)
$mg.Dispose()
$maskName = "practical-test-mask.png"
$maskPath = Join-Path $inputDir $maskName
$maskBmp.Save($maskPath, [System.Drawing.Imaging.ImageFormat]::Png)
$maskBmp.Dispose()
Write-Step "Full-document mask saved: $maskPath ($docW x $docH, inpaint region = ($cropL, $cropT, $cropW, $cropH))"

# --- Step 4: build workflow from production JSON ---
Write-Step "Reading production workflow + mapping"
$workflow = Get-Content -Raw -Path $workflowPath | ConvertFrom-Json | ConvertTo-Hashtable
$mapping = Get-Content -Raw -Path $mappingPath | ConvertFrom-Json

# --- Step 5: set workflow inputs via mapping (production code path) ---
function Set-MappingInput {
    param($Workflow, $Inputs, $Path, $Value)
    $item = $Inputs.$Path
    if (-not $item) { return }
    if ($item -is [array]) {
        foreach ($target in $item) {
            $Workflow[$target.nodeId].inputs.$($target.inputName) = $Value
        }
    } else {
        $Workflow[$item.nodeId].inputs.$($item.inputName) = $Value
    }
}

$negPrompt = "hard square edges, visible seams, distorted hands, extra fingers, unreadable artifacts, duplicated object, damaged background"

Set-MappingInput $workflow $mapping.inputs "sourceImage" $sourceName
Set-MappingInput $workflow $mapping.inputs "selectionMask" $maskName
Set-MappingInput $workflow $mapping.inputs "prompt" $Prompt
Set-MappingInput $workflow $mapping.inputs "negativePrompt" $negPrompt
Set-MappingInput $workflow $mapping.inputs "cfg" 1
Set-MappingInput $workflow $mapping.inputs "seed" 12345
Set-MappingInput $workflow $mapping.inputs "seedRandomize" "disable"
Set-MappingInput $workflow $mapping.inputs "lorasJson" "[]"
Set-MappingInput $workflow $mapping.inputs "steps" $Steps

# Width/height multi-target (ModelSamplingFlux + Flux2Scheduler)
if ($mapping.inputs.width) { foreach ($t in $mapping.inputs.width) { $workflow[$t.nodeId].inputs.$($t.inputName) = $docW } }
if ($mapping.inputs.height) { foreach ($t in $mapping.inputs.height) { $workflow[$t.nodeId].inputs.$($t.inputName) = $docH } }
# Crop + doc dims go to node 91 (RasterRelayPadToDocument)
Set-MappingInput $workflow $mapping.inputs "cropLeft" $cropL
Set-MappingInput $workflow $mapping.inputs "cropTop" $cropT
Set-MappingInput $workflow $mapping.inputs "cropWidth" $cropW
Set-MappingInput $workflow $mapping.inputs "cropHeight" $cropH
Set-MappingInput $workflow $mapping.inputs "docWidth" $docW
Set-MappingInput $workflow $mapping.inputs "docHeight" $docH

$workflow["80"].inputs.filename_prefix = $OutputSubdir

# --- Step 6: submit ---
$payload = @{ client_id = "rasterrelay-practical"; prompt = $workflow }
$body = $payload | ConvertTo-Json -Depth 100
Write-Step "Submitting workflow to /prompt. Steps=$Steps, prompt='$Prompt'"
$submitStart = Get-Date
$resp = Invoke-RestMethod -Uri "$ComfyUrl/prompt" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 60
if ($resp.node_errors -and $resp.node_errors.PSObject.Properties.Count -gt 0) {
    throw "ComfyUI returned node_errors: $($resp.node_errors | ConvertTo-Json -Depth 20)"
}
$promptId = $resp.prompt_id
Write-Step "Prompt queued: $promptId"

# --- Step 7: poll /history ---
$deadline = (Get-Date).AddSeconds(900)
$historyEntry = $null
do {
    Start-Sleep -Seconds 4
    $h = Invoke-RestMethod -Uri "$ComfyUrl/history/$promptId" -TimeoutSec 20
    if ($h.PSObject.Properties.Name -contains $promptId) {
        $historyEntry = $h.$promptId
        break
    }
} while ((Get-Date) -lt $deadline)
if (-not $historyEntry) { throw "Timeout waiting for $promptId" }

$elapsed = (Get-Date) - $submitStart
Write-Step "Workflow finished in $([int]$elapsed.TotalSeconds)s. status=$($historyEntry.status.status_str)"
if ($historyEntry.status.status_str -ne "success") {
    throw "Workflow failed: $($historyEntry.status | ConvertTo-Json -Depth 20)"
}

# --- Step 8: find output image ---
$firstImage = $null
foreach ($outputProperty in $historyEntry.outputs.PSObject.Properties) {
    $images = $outputProperty.Value.images
    if ($images -and $images.Count -gt 0) {
        $firstImage = $images[0]
        break
    }
}
if (-not $firstImage) { throw "No output image returned" }

# The result from RasterRelayPadToDocument is the full document size (RGBA) -- filename
$resultFilename = $firstImage.filename
$resultSubfolder = $firstImage.subfolder
$resultFullPath = Join-Path (Join-Path $outputDir $resultSubfolder) $resultFilename
Write-Step "Result PNG: $resultFullPath"

# Download to a local test directory for inspection
$localResultDir = Join-Path $repoRoot "Testy\Wyniki testów\$(Get-Date -Format 'yyyy-MM-dd-HHmmss')-practical-test"
New-Item -ItemType Directory -Path $localResultDir -Force | Out-Null
$localResultPath = Join-Path $localResultDir "padded-output.png"
Copy-Item $resultFullPath $localResultPath
Copy-Item $sourcePath (Join-Path $localResultDir "cropped-source.png")
Copy-Item $maskPath (Join-Path $localResultDir "mask-full-doc.png")
# Also export the document-sized source PNG (so we can compare inpaint side-by-side)
$docSourcePath = Join-Path $inputDir "practical-test-doc-source.png"
$docBmp.Save($docSourcePath, [System.Drawing.Imaging.ImageFormat]::Png)
Copy-Item $docSourcePath (Join-Path $localResultDir "doc-source.png")
$docBmp.Dispose()
Write-Step "All artifacts copied to: $localResultDir"

# --- Step 9: verify alpha channel ---
$img = [System.Drawing.Image]::FromFile($resultFullPath)
try {
    Write-Step "Result dimensions: $($img.Width) x $($img.Height), PixelFormat: $($img.PixelFormat)"
    if ($img.Width -ne $docW -or $img.Height -ne $docH) {
        throw "Expected ${docW}x${docH}, got $($img.Width)x$($img.Height)"
    }

    # Sample alpha at corners (should be 0 = transparent) and inside the inpaint region (should be opaque)
    $corners = @(
        @{ x = 1; y = 1; label = "top-left" },
        @{ x = $img.Width - 2; y = 1; label = "top-right" },
        @{ x = 1; y = $img.Height - 2; label = "bottom-left" },
        @{ x = $img.Width - 2; y = $img.Height - 2; label = "bottom-right" }
    )
    $outsideAlpha = @()
    foreach ($c in $corners) {
        $px = $img.GetPixel($c.x, $c.y)
        $outsideAlpha += $px.A
        Write-Step "  outside-crop pixel ($($c.label)) alpha=$($px.A), rgb=($($px.R),$($px.G),$($px.B))"
    }
    if (($outsideAlpha | Measure-Object -Maximum).Maximum -gt 8) {
        throw "Pixels outside the crop should be transparent, found alpha up to $(($outsideAlpha | Measure-Object -Maximum).Maximum)"
    }
    Write-Step "  outside-crop alpha OK (max=$(($outsideAlpha | Measure-Object -Maximum).Maximum))"

    # Sample center of the inpaint region (should be opaque)
    $cx = $cropL + [int]($cropW / 2)
    $cy = $cropT + [int]($cropH / 2)
    $centerPx = $img.GetPixel($cx, $cy)
    Write-Step "  inpaint-center pixel ($cx,$cy) alpha=$($centerPx.A), rgb=($($centerPx.R),$($centerPx.G),$($centerPx.B))"
    if ($centerPx.A -lt 200) {
        throw "Inpaint center should be opaque, got alpha=$($centerPx.A)"
    }
    Write-Step "  inpaint-center alpha OK"
} finally {
    $img.Dispose()
}

Write-Step "PRACTICAL TEST SUCCEEDED."
Write-Step "Artifacts: $localResultDir"
Write-Step "  - doc-source.png       (original full-doc image, $docW x $docH)"
Write-Step "  - cropped-source.png   (the $cropW x $cropH crop fed to ComfyUI)"
Write-Step "  - mask-full-doc.png    (full-doc mask, inpaint region white, rest black)"
Write-Step "  - padded-output.png    (the result returned by RasterRelayPadToDocument)"
