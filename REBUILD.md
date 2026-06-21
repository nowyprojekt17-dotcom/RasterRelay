# RasterRelay — Rebuild Map

Stan po resecie (`d88835d`): projekt zwinięty do **shellu aplikacji**. Stary pipeline
inpaintingu (custom nodes, workflow, łańcuch koloru, testy, skrypty audytu) usunięty.
Ten plik mapuje, co zostało i gdzie wpiąć nowe podejście. Stary kod jest w historii
gita sprzed `d88835d`, gdyby trzeba coś odzyskać.

## Co zostało (reużywalny shell)

| Część | Plik | Rola |
|---|---|---|
| Launcher (Tauri+React) | `launcher/src-tauri/src/lib.rs` | skan ComfyUI, instal LoRA/GGUF, start ComfyUI/Photoshop/UXP, ładowanie panelu |
| Launcher UI | `launcher/src/App.tsx` | readiness, centrum jakości, LoRA stack |
| Panel Photoshop (UXP) | `photoshop_plugin/src/panel.js` | eksport dokumentu, maska, upload do ComfyUI, submit, placement wyniku, ICC→sRGB |
| Panel helpers | `photoshop_plugin/src/panel-helpers.js` | resolveQualityPlan, computeOptimalGenSize, edit-mode plan |
| Brand / referencje | `assets/brand/`, `test-images/` | logo + obrazy testowe |
| Skrypty | `scripts/{create-desktop-shortcut.ps1, load-uxp-plugin.mjs}` | shortcut + loader UXP |

## Kontrakt styku z nowym workflow

Shell jest **mapping-driven** i w dużej części gotowy na nowy graf:

- **`panel.js` `applyWorkflowInputs`** ustawia `mapping.inputs.<klucz> → [nodeId, slot]`.
  Stare klucze koloru (`refineSource`, `backgroundPreserveThreshold`, `toneRadius`,
  `chromaRadius`) są osłonięte `if (mapping.inputs.X)` — nowy mapping bez nich je pomija.
  Klucze rdzeniowe, których nowy workflow nadal potrzebuje: `sourceImage`, `selectionMask`,
  `prompt`, `negativePrompt`, `steps`, `cfg`, `seed`, `seedRandomize`, `width`, `height`,
  `crop{Left,Top,Width,Height}`, `doc{Width,Height}`, `lorasJson`.

- **Sloty plików workflow** (puste po resecie, launcher je instaluje):
  `photoshop_plugin/workflows/inpainting-api.json` + `inpainting-api.mapping.json`.

- **Twardo zaszyte do zmiany** — `lib.rs` `workflow_required_classes()` (~l. 1998):
  lista klas węzłów, w tym usunięte `RasterRelay{LoraStack,PadToDocument,ReferenceColorLock,SaveImage}`.
  Readiness nie przejdzie, póki ta lista nie opisze klas NOWEGO grafu.

## Środowisko (bez zmian)

ComfyUI `127.0.0.1:8188`. Launcher uruchamia izolowany runtime w
`%TEMP%\RasterRelay\comfy-runtime`. Wymagane modele (zaszyte w `lib.rs`):
`flux-2-klein-9b-Q4_K_M.gguf` (unet), `qwen_3_8b_fp8mixed.safetensors` (text enc),
`flux2-vae.safetensors` (vae). Custom nodes instalowane jako KOPIA → po edycji
reinstal + restart ComfyUI.

## Lekcje z usuniętego pipeline'u (warte uwagi przy projektowaniu nowego)

- Klein GGUF ignoruje concat conditioning → InpaintModelConditioning bezużyteczny;
  działa DifferentialDiffusion (soft maska).
- Korekta koloru tylko przy szwie (seam-band) — wnętrze obiektu ma prawo różnić się od tła.
- Upscale małych wycinków NIE poprawia ostrości na Flux2 Klein (zmierzone). Generuj natywnie ≤~1.15MP.
- ICC: PNG z ComfyUI bez tagu → dokument roboczy PS trzymaj w sRGB.

## Do zdecydowania przed rozbudową

1. Czy nowe podejście zostaje na ComfyUI + lokalny Flux Klein, czy zmienia silnik/host?
2. Jaki jest nowy graf inpaintingu (od tego zależy `workflow_required_classes()` i klucze mappingu)?
3. Czy stripować z `panel.js`/`lib.rs` martwy kontrakt starego łańcucha koloru teraz,
   czy zostawić osłonięty (no-op) do czasu zdefiniowania nowego grafu?
