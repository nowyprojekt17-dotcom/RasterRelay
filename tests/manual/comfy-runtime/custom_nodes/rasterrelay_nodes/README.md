# RasterRelay Custom Nodes for ComfyUI

Custom nodes for the RasterRelay Photoshop-to-ComfyUI inpainting bridge.

## Nodes

Two groups: **active** nodes are wired into the production workflow
(`photoshop_plugin/workflows/inpainting-api.json`); **library** nodes (marked
`(biblioteka)` in the ComfyUI menu) are kept as building blocks / earlier
experiments but are not in the default graph.

### Active (production pipeline)

| Node | Rola |
|------|------|
| `RasterRelayLoraStack` | Łańcuch LoRA z JSON |
| `RasterRelayMaskEdgeRefine` | Maska kompozycji klei się do krawędzi obrazu (guided filter) |
| `RasterRelayVaeDriftMatch` | Przywraca oryginalne piksele poza maską (dryf VAE/skali) |
| `RasterRelayBackgroundPreserve` | W masce: dryf modelu → oryginał, intencja → generacja |
| `RasterRelayColorCalibrate` | Inwersja systematycznego castu koloru modelu (intent-safe) |
| `RasterRelaySeamlessTone` | Bezszwowe dopasowanie tonu (dyfuzja LF; tryb full + chroma) |
| `RasterRelayGrainTransfer` | Ciągłość ziarna fotograficznego (tłumi krawędzie) |
| `RasterRelayPadToDocument` | Skaluje/wkleja wynik do rozmiaru dokumentu z alfą |
| `RasterRelaySaveImage` | Zapis PNG z kanałem alfa |

Kolejność w workflow:

```text
gen(DifferentialDiffusion) -> VAEDecode -> [skala→natywna]
  -> MaskEdgeRefine -> VaeDriftMatch -> BackgroundPreserve -> ColorCalibrate
  -> [opcjonalny refine pass: preset Maks]
  -> SeamlessTone(full) -> SeamlessTone(chroma) -> GrainTransfer
  -> PadToDocument -> SaveImage
```

### Library (nie w domyślnym workflow)

`RasterRelaySelectionMask`, `RasterRelaySmartCropAligner`,
`RasterRelaySmartCropTrimmer`, `RasterRelayMaskCropper`,
`RasterRelayAreaMatch`, `RasterRelayColorHarmonize`, `RasterRelayColorMatch`,
`RasterRelayEdgeHarmonize` — pomocniki i wcześniejsze podejścia do koloru.
`AreaMatch`/`ColorHarmonize` (globalny Reinhard) zostały **zmierzone jako gorsze
od `SeamlessTone`** i zastąpione; zostają jako materiał referencyjny.

> Po edycji dowolnego węzła uruchom `scripts/reload-rasterrelay-nodes.ps1`
> (reinstall + restart + sprawdzenie gotowości) — węzły instalują się jako kopia.

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
