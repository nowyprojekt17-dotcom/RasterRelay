param(
    [string]$SourceImage = "C:\Users\Mierz\Desktop\RasterRelay\tests\manual\test-images\envato-labs-ai-da532839-090d-4b70-9e60-1ed61c2e94a5.jpg",
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$testScript = Join-Path $repoRoot "comfy_nodes\tests\practical_alignment_test.py"

if (-not (Test-Path -LiteralPath $testScript)) {
    throw "Missing practical alignment test script: $testScript"
}

if (-not (Test-Path -LiteralPath $SourceImage)) {
    throw "Missing source image: $SourceImage"
}

if ($OutputRoot) {
    python $testScript --source-image $SourceImage --output-root $OutputRoot
} else {
    python $testScript --source-image $SourceImage
}
if ($LASTEXITCODE -ne 0) {
    throw "Practical alignment test failed with exit code $LASTEXITCODE"
}
