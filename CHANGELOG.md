# Changelog

Wszystkie znaczące zmiany w tym projekcie będą dokumentowane w tym pliku.

Format bazuje na [Keep a Changelog](https://keepachangelog.com/pl/1.0.0/),
a ten projekt adheres to [Semantic Versioning](https://semver.org/lang/pl/).

## [Unreleased]

### Added
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
