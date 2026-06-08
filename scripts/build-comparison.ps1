param(
    [Parameter(Mandatory = $true)]
    [string]$SourceImage,
    [Parameter(Mandatory = $true)]
    [string]$CroppedImage,
    [Parameter(Mandatory = $true)]
    [string]$ResultImage,
    [string]$OutputImage = "",
    [int]$CropLeft = 256,
    [int]$CropTop = 224,
    [int]$CropWidth = 512,
    [int]$CropHeight = 320
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

if (-not $OutputImage) {
    $OutputImage = Join-Path (Split-Path -Parent $ResultImage) "comparison.png"
}

function Load-Bmp($path) {
    $bmp = New-Object System.Drawing.Bitmap $path
    return $bmp
}

# Composite the result on top of the source so the user can see the inpaint as it would appear in Photoshop
$source = Load-Bmp $SourceImage
$result = Load-Bmp $ResultImage

if ($source.Width -ne $result.Width -or $source.Height -ne $result.Height) {
    throw "Source and result dimensions differ: $($source.Width)x$($source.Height) vs $($result.Width)x$($result.Height)"
}

$composited = New-Object System.Drawing.Bitmap $source.Width, $source.Height
$g = [System.Drawing.Graphics]::FromImage($composited)
$g.DrawImage($source, 0, 0)

# Now overlay the result using its alpha
$ia = [System.Drawing.Imaging.ImageAttributes]::new()
$cm = New-Object System.Drawing.Imaging.ColorMatrix ([float[]]@(
    1,0,0,0,0,
    0,1,0,0,0,
    0,0,1,0,0,
    0,0,0,1,0,
    0,0,0,0,1
))
$ia.SetColorMatrix($cm)
$g.DrawImage($result, (New-Object System.Drawing.Rectangle 0, 0, $result.Width, $result.Height), 0, 0, $result.Width, $result.Height, [System.Drawing.GraphicsUnit]::Pixel, $ia)
$g.Dispose()
$ia.Dispose()

# Build the side-by-side comparison: original | crop | result-on-top-of-original
$w = $source.Width
$h = $source.Height
$sideBySide = New-Object System.Drawing.Bitmap ($w * 3 + 40), ($h + 60)
$gs = [System.Drawing.Graphics]::FromImage($sideBySide)
$gs.Clear([System.Drawing.Color]::Black)
$gs.DrawImage($source, 0, 30)
$gs.DrawImage((Load-Bmp $CroppedImage), ($w + 20), 30)
$gs.DrawImage($composited, ($w * 2 + 40), 30)

# Labels
$font = New-Object System.Drawing.Font "Arial", 16, ([System.Drawing.FontStyle]::Bold)
$brush = [System.Drawing.Brushes]::White
$gs.DrawString("1. SOURCE ($($source.Width)x$($source.Height))", $font, $brush, 0, 5)
$gs.DrawString("2. CROPPED INPUT ($($CropWidth)x$($CropHeight))", $font, $brush, ($w + 20), 5)
$gs.DrawString("3. RESULT composited on source", $font, $brush, ($w * 2 + 40), 5)

# Red rectangle showing crop region on source
$cropPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::Red), 4
$gs.DrawRectangle($cropPen, $CropLeft, 30 + $CropTop, $CropWidth, $CropHeight)
$gs.DrawRectangle($cropPen, ($w + 20), 30, $CropWidth, $CropHeight)
$gs.DrawRectangle($cropPen, ($w * 2 + 40 + $CropLeft), 30 + $CropTop, $CropWidth, $CropHeight)

$gs.Dispose()
$sideBySide.Save($OutputImage, [System.Drawing.Imaging.ImageFormat]::Png)
$source.Dispose()
$result.Dispose()
$composited.Dispose()

Write-Host "Comparison saved to: $OutputImage"
