# RasterRelay Custom Nodes for ComfyUI

Custom nodes for the RasterRelay Photoshop-to-ComfyUI inpainting bridge.

## Nodes

| Node | Category | Description |
|------|----------|-------------|
| `RasterRelaySelectionMask` | RasterRelay | Creates MASK tensor from raw selection pixel data with GPU feathering |
| `RasterRelayLoraStack` | RasterRelay | Applies multiple LoRA models from JSON configuration |
| `RasterRelayPadToDocument` | RasterRelay | Resizes a generated crop, pads it back to full document dimensions, and keeps the full crop present by default |
| `RasterRelaySmartCropAligner` | RasterRelay | Expands a Photoshop crop to model-safe grid dimensions without resizing pixels |
| `RasterRelaySmartCropTrimmer` | RasterRelay | Removes grid-alignment padding and restores the original crop dimensions |
| `RasterRelayGrainInjector` | RasterRelay | Adds reference-matched micro-grain to generated regions |
| `RasterRelayVaeDriftMatch` | RasterRelay | Restores unmasked original pixels after generation to remove VAE/scale/color drift |
| `RasterRelayColorHarmonize` | RasterRelay | Matches colors of generated region to surrounding original using Reinhard LAB transfer |

## Alignment workflow

The alignment nodes are designed for Photoshop edits where users may later adjust the generated layer mask. The safest order is:

```text
SmartCropAligner -> model/VAE path -> SmartCropTrimmer -> VaeDriftMatch -> ColorHarmonize -> PadToDocument -> SaveImage
```

`RasterRelaySmartCropAligner` avoids the common "slightly zoomed" look by padding the crop outward to a grid-safe size instead of scaling the crop. `RasterRelayVaeDriftMatch` should run late in the chain because it restores every pixel where the mask is `0` back to the exact Photoshop source pixel.

For Photoshop layer-mask output, `RasterRelayVaeDriftMatch` defaults to `mask_mode = binary`. Any pixel where the mask is greater than zero keeps the full generated content; only exactly unmasked pixels are restored from the original. This prevents double-feathering, because Photoshop's layer mask is responsible for edge softness.

`RasterRelayPadToDocument` defaults to `alpha_mode = crop`. The saved PNG contains the whole generated crop as layer content, while the Photoshop layer mask controls the visible selection shape. Use `alpha_mode = mask` only for legacy behavior where PNG transparency follows the selection mask directly.

RasterRelay uses a dual-mask handoff for FLUX.2 inpainting. The mask uploaded to ComfyUI is a generation/denoise support mask with an automatic quality-dependent halo, while the Photoshop layer mask remains the user-facing visibility mask. This gives FLUX.2 Klein more transition context without making the final layer visibly larger.

`RasterRelayColorHarmonize` addresses color mismatch between the AI-generated inpainted region and the surrounding original image. It uses Reinhard color transfer in LAB color space to match the color statistics (mean and standard deviation) of the generated region to the reference area around the mask. The node applies correction only inside the mask with Gaussian-blurred edges for seamless blending.

Parameters:
- `strength` (0.0-1.0): Intensity of color correction. 0.0 leaves the image unchanged, 1.0 applies full correction.
- `blend_radius` (0-50): Radius of Gaussian blur at mask edges for smooth transitions.
- `margin` (5-100): Pixel margin around the mask used to sample reference color statistics from the original image.

ColorHarmonize should run after `VaeDriftMatch` in the pipeline. While `VaeDriftMatch` restores exact original pixels in unmasked regions, `ColorHarmonize` fixes the color tone inside the generated region to match the surrounding context.

Automatic color/tonal harmonization is now available through `RasterRelayColorHarmonize` as an optional post-processing step. It is not applied by default, allowing users to control color correction intensity per-image.

## Tests

Unit tests can be run directly:

```powershell
python comfy_nodes/tests/match_and_align_test.py
python comfy_nodes/tests/pad_to_document_test.py
python comfy_nodes/tests/lora_stack_test.py
```

The practical alignment regression test uses a real source image and a non-grid crop (`317x413`) to validate grid-safe alignment, trimming, drift restoration, and final RGBA padding without running a full ComfyUI generation:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/practical-alignment-test.ps1
```

It writes artifacts and `REPORT.md` under `tests/manual/test-results/<timestamp>-alignment-practical-test`.

## LoRA behavior

`RasterRelayLoraStack` accepts a JSON array in `loras_json`:

```json
[
  {
    "name": "style.safetensors",
    "strength_model": 0.8,
    "strength_clip": 0.8
  }
]
```

An empty array (`[]`) means "run without LoRA".

If a requested LoRA is missing or the JSON is invalid, the node raises an error instead of silently skipping it. This is intentional: RasterRelay should not pretend that a selected LoRA was used when it was not.

## API Endpoints

### `POST /rasterrelay/upload-selection`

Uploads raw Photoshop selection pixel data, creates a mask PNG with feathering, and saves it to ComfyUI's input directory.

Request body (JSON):
```json
{
  "pixels": "<base64-encoded uint8 array>",
  "sel_width": 200,
  "sel_height": 150,
  "full_width": 1024,
  "full_height": 1024,
  "sel_left": 96,
  "sel_top": 96,
  "feather": 36
}
```

## Installation

Copy the `comfy_nodes` directory into `ComfyUI/custom_nodes/rasterrelay_nodes`.
