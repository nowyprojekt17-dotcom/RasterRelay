# Changelog

Wszystkie znaczące zmiany w tym projekcie będą dokumentowane w tym pliku.

Format bazuje na [Keep a Changelog](https://keepachangelog.com/pl/1.0.0/),
a ten projekt adheres to [Semantic Versioning](https://semver.org/lang/pl/).

## [Unreleased]

### Added (Faza D — guard-rail rozdzielczości generacji)
- `computeOptimalGenSize` w panel-helpers + węzły skalowania w workflow:
  wycinki ≤ ~1.15 MP generują NATYWNIE (zmierzono: upscale małych wycinków
  na Flux2 Klein nie daje ostrości, a osłabia edycję); wycinki większe są
  kontrolowanie zmniejszane do ~1.15 MP (ochrona VRAM i jakości modelu),
  a wynik wraca do natywnej rozdzielczości przed deterministycznym
  post-processingiem. Test 2.79 MP: szew 0.0012 (rekord), zmiana poza
  maską 0.00001.

### Added (Faza B + kalibracja odpowiedzi barwnej)
- **Refine pass**: po złożeniu etapu 1 krótki przebieg niskim denoise (0.18)
  po całym wycinku — ujednolica ziarno/ostrość/odpowiedź barwną i roztapia
  wewnętrzne granice keep/restore. Sterowane mappingiem (`refineDenoise`,
  `refineSeed`).
- **Węzeł `RasterRelayColorCalibrate`** (pomysł użytkownika, ulepszony):
  mierzy afiniczny dryf barwny modelu na pikselach, które miały zostać
  niezmienione (populacja dryfu), i odwraca go na całym wyniku — zdejmuje
  systematyczny cast także z obszaru INTENCJI, nie cofając zmiany
  semantycznej (transformacja afiniczna nie odwróci brąz→zieleń).
  Klucz mappingu `calibrateStrength`.
- Łańcuch produkcyjny: gen(DD) → VDM → BgPreserve → [refine 0.18] →
  ColorCalibrate → VDM → BgPreserve → SeamlessTone×2 → Grain → Pad.

### Fixed (hotfix po realnych testach: zielone włosy + usuwanie obiektów)
- **SeamlessTone niszczył intencjonalne edycje**: pełna korekta tonu na całym
  wnętrzu maski ciągnęła np. zielone włosy do beżu otoczenia (+0.13 jasności,
  zieleń z +0.066 do zera). Teraz korekta jest ważona pasmem szwu
  (`interior_strength`, `seam_band=24px`): pełna przy granicy, śladowa w głębi.
  Zieleń zachowana w ~60%, szew bez regresji.
- **GrainTransfer odrysowywał kontury usuwanych obiektów**: rezyduum
  wysokoczęstotliwościowe na krawędziach (±0.3) to struktura, nie ziarno.
  Teraz krawędzie są tłumione (zerowane z dylatacją ~3px, `grain_clip=0.04`)
  — usuwanie obiektów czyste, ziarno nadal przenoszone.
- **MaskEdgeRefine prowadzony obrazem WYGENEROWANYM** (nie oryginałem):
  przy usuwaniu krawędzie usuwanego obiektu nie przyciągają już maski.

### Added
- **Węzeł `RasterRelaySeamlessTone`** — bezszwowe dopasowanie jasności/koloru
  przez dyfuzję tonu otoczenia do wnętrza maski (niska częstotliwość,
  zachowuje detal, naprawia też gradienty światła). Rozwiązuje główny problem
  niespójności wygenerowanego fragmentu. Zmierzona poprawa szwu ~26% vs surowa
  generacja i vs stary łańcuch Reinharda.
- Przebudowany od zera `photoshop_plugin/workflows/inpainting-api.json`:
  `VAEDecode → VaeDriftMatch → SeamlessTone → PadToDocument → SaveImage`.
- `tone_radius` auto-skalowany w `panel.js` wg rozmiaru wycinka (klucze
  `toneRadius`/`toneStrength` w mappingu).
- Testy jednostkowe `seamless_tone_test.py` (5 testów).

### Changed
- Usunięto z aktywnego workflow nieskuteczny łańcuch `AreaMatch + ColorHarmonize`
  (globalny Reinhard pogarszał szew); węzły zostają w bibliotece.

### Added (wcześniej)
- Testy jednostkowe dla `grain_transfer.py` (6 testów)
- Testy jednostkowe dla `edge_harmonize.py` (7 testów)
- Wspólny moduł `comfy_nodes/utils/mask_processing.py` z funkcjami `blur_mask` i `gaussian_kernel`
- Zarządzanie pamięcią GPU (`torch.cuda.empty_cache()`) w kluczowych nodes

### Changed
- Naprawiono kodowanie UTF-8 w `launcher/src/App.tsx` (10 linii)
- Naprawiono kodowanie UTF-8 w `launcher/src-tauri/src/lib.rs` (11 linii)
- Naprawiono brakujące polskie znaki diakrytyczne w `photoshop_plugin/src/panel.js` (8 linii)
- Usunięto duplikat katalogu `photoshop_plugin/comfy_nodes`
- Zastąpiono duplikaty kodu `_blur_mask` w `color_harmonize.py` i `selection_mask.py` importem z wspólnego modułu
- Dodano walidację parametrów w `pad_to_document.py` (ujemne offsety, wymiary, bounds)
- Dodano walidację wymiarów i zakresów w `comfy_nodes/server/api.py`
- Dodano walidację wymiarów crop i obsługę edge cases w `mask_cropper.py`

### Fixed
- Zapobieganie crashom przy nieprawidłowych danych wejściowych
- Niespójność w kodowaniu polskich znaków w UI
- Duplikacja kodu w przetwarzaniu masek

## [0.1.0] - 2026-06-11

### Initial Release
- Podstawowa funkcjonalność RasterRelay
- Nodes dla ComfyUI: selection_mask, pad_to_document, save_image_rgba, match_and_align, color_harmonize, grain_transfer, edge_harmonize
- Plugin Photoshop z panelem UXP
- Launcher Tauri z integracją ComfyUI
- Workflow API dla inpaintingu

---

## Legenda

- `Added` - Nowe funkcjonalności
- `Changed` - Zmiany w istniejącej funkcjonalności
- `Deprecated` - Funkcjonalności które zostaną usunięte
- `Removed` - Usunięte funkcjonalności
- `Fixed` - Naprawione błędy
- `Security` - Zmiany związane z bezpieczeństwem
