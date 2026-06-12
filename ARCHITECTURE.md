# Architektura Projektu RasterRelay

## Przegląd

RasterRelay to system do zaawansowanego inpaintingu obrazów, łączący trzy główne komponenty:
1. **ComfyUI Nodes** - przetworzenie obrazu w Pythonie
2. **Photoshop Plugin** - interfejs użytkownika w Photoshopie
3. **Launcher** - aplikacja desktopowa Tauri

## Diagram Przepływu Danych

```
┌─────────────────────────────────────────────────────────────┐
│                    Photoshop Plugin                          │
│  ┌──────────────┐                                           │
│  │  Panel UI    │ ← Użytkownik wybiera obszar, wpisuje prompt│
│  └──────┬───────┘                                           │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────┐                                           │
│  │ Export PNG   │ ← Eksportuje zaznaczony obszar + maskę    │
│  └──────┬───────┘                                           │
└─────────┼───────────────────────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────────────────────────────┐
│              ComfyUI Workflow (inpainting-api.json, 41 nodes)       │
│                                                                    │
│  GENERACJA (w optymalnej rozdzielczości — Faza D guard-rail):      │
│    LoadImage+Mask ─▶ ImageScale/ResizeMask ─▶ VAEEncode            │
│      ─▶ SetLatentNoiseMask ─▶ Sampler(Flux2, +DifferentialDiff)    │
│      ─▶ VAEDecode ─▶ ImageScale→native                             │
│                          │                                         │
│  POST (deterministyczny, w rozdzielczości natywnej vs oryginał):   │
│    MaskEdgeRefine(guide=gen) ─▶ VaeDriftMatch(restore poza maską)  │
│      ─▶ BackgroundPreserve(dryf w masce→oryginał)                  │
│      ─▶ ColorCalibrate(zdjęcie castu modelu — ZAWSZE)             │
│                          │                                         │
│            ┌─────────────┴── refineSource (PRESET) ──┐            │
│      Fast/Balanced (93)                    Maks (89)  │            │
│            │                  refine: encode→denoise 0.18→decode   │
│            │                    →VaeDriftMatch→BackgroundPreserve  │
│            └─────────────┬───────────────────────────┘            │
│                          ▼                                         │
│      SeamlessTone(full, seam-band) ─▶ SeamlessTone(chroma)         │
│      ─▶ GrainTransfer ─▶ PadToDocument ─▶ SaveImage(RGBA)          │
└────────────────────────────┼───────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    Photoshop Plugin (Import)                 │
│  ┌──────────────┐                                           │
│  │ Import Layer │ ← Importuje wynik jako nową warstwę       │
│  └──────────────┘                                           │
└─────────────────────────────────────────────────────────────┘
```

## Struktura Katalogów

### Główna struktura projektu
```
RasterRelay/
├── comfy_nodes/          # Nodes ComfyUI (Python)
├── photoshop_plugin/     # Plugin Photoshop (JavaScript)
├── launcher/             # Aplikacja desktop (TypeScript/Rust)
├── docs/                 # Dokumentacja
├── scripts/              # Skrypty PowerShell
├── tests/                # Testy
│   ├── *.py              # Skrypty testowe
│   └── manual/           # Testy ręczne
│       ├── test-images/  # Obrazy testowe
│       └── test-results/ # Wyniki testów
├── workflows/            # Workflow JSON
└── assets/               # Zasoby
```

### `comfy_nodes/` - Nodes ComfyUI
```
comfy_nodes/
├── nodes/                      # Implementacje nodes
│   ├── selection_mask.py       # Tworzenie maski z zaznaczenia
│   ├── pad_to_document.py      # Rozszerzenie do rozmiaru dokumentu
│   ├── save_image_rgba.py      # Zapis PNG z kanałem alfa
│   ├── match_and_align.py      # AKTYWNY: VaeDriftMatch (+ SmartCrop/Grain biblioteka)
│   ├── seamless_tone.py        # AKTYWNY: bezszwowy ton (dyfuzja LF, full+chroma)
│   ├── background_preserve.py  # AKTYWNY: dryf w masce → oryginał
│   ├── color_calibrate.py      # AKTYWNY: inwersja castu modelu (pomysł usera)
│   ├── mask_edge_refine.py     # AKTYWNY: maska klei się do krawędzi (guided filter)
│   ├── grain_transfer.py       # AKTYWNY: ciągłość ziarna (tłumi krawędzie)
│   ├── pad_to_document.py      # AKTYWNY: rozszerzenie do dokumentu
│   ├── lora_stack.py           # AKTYWNY: stos LoRA
│   ├── save_image_rgba.py      # AKTYWNY: zapis PNG z alfą
│   ├── color_harmonize.py      # biblioteka (zastąpiony przez SeamlessTone)
│   ├── color_match.py          # biblioteka
│   ├── edge_harmonize.py       # biblioteka
│   ├── area_match.py           # biblioteka (zastąpiony)
│   ├── mask_cropper.py         # biblioteka
│   └── selection_mask.py       # biblioteka
├── server/                     # API endpoints
│   └── api.py                  # Endpointy dla upload-selection
├── utils/                      # Wspólne funkcje
│   ├── __init__.py
│   └── mask_processing.py      # blur_mask, gaussian_kernel
└── tests/                      # Testy jednostkowe
    ├── color_harmonize_test.py
    ├── grain_transfer_test.py
    ├── edge_harmonize_test.py
    ├── match_and_align_test.py
    ├── pad_to_document_test.py
    └── practical_alignment_test.py
```

### `photoshop_plugin/` - Plugin Photoshop
```
photoshop_plugin/
├── src/                        # Kod źródłowy
│   ├── panel.js                # Główny panel UI (2800+ linii)
│   ├── panel-helpers.js        # Funkcje pomocnicze (430 linii)
│   └── styles.css              # Style CSS
├── workflows/                  # Workflow JSON
│   ├── inpainting-api.json
│   └── inpainting-api.mapping.json
├── tests/                      # Testy JavaScript
│   └── panel-helpers.test.js
└── test_assets/                # Zasoby testowe
```

### `launcher/` - Aplikacja Desktop
```
launcher/
├── src/                        # Frontend (TypeScript/React)
│   ├── App.tsx                 # Główny komponent React
│   ├── main.tsx                # Entry point
│   └── styles/                 # Style CSS
├── src-tauri/                  # Backend (Rust)
│   ├── src/
│   │   ├── main.rs             # Entry point Tauri
│   │   └── lib.rs              # Logika aplikacji (3500+ linii)
│   └── Cargo.toml              # Zależności Rust
└── package.json                # Zależności Node.js
```

## Kluczowe Moduły

### 1. Przetwarzanie Masek (`mask_processing.py`)

Wspólne funkcje używane przez wszystkie nodes:

```python
# Gaussian blur maski (separable convolution)
def blur_mask(mask: torch.Tensor, blend_radius: int) -> torch.Tensor

# Tworzenie kernela Gaussa
def gaussian_kernel(kernel_size: int, sigma: float) -> torch.Tensor
```

**Zastosowanie:**
- `color_harmonize.py` - harmonizacja kolorów
- `grain_transfer.py` - transfer ziarna
- `edge_harmonize.py` - harmonizacja krawędzi
- `match_and_align.py` - dopasowanie VAE drift

### 2. Przepływ Danych w Workflow

```
1. User zaznacza obszar w Photoshopie
   ↓
2. panel.js eksportuje:
   - Obraz PNG (zaznaczony obszar)
   - Maska PNG (zaznaczenie)
   - Metadane (wymiary, offsety)
   ↓
3. ComfyUI Nodes przetwarzają (kolejność z inpainting-api.json):
   a) ImageScale/ResizeMask  - skalowanie do optymalnej rozdzielczości (Faza D)
   b) VAEEncode + SetLatentNoiseMask + sampler Flux (+DifferentialDiffusion)
   c) ImageScale → powrót do rozdzielczości natywnej
   d) mask_edge_refine.py    - maska kompozycji klei się do krawędzi (guide=gen)
   e) match_and_align.py     - VaeDriftMatch przywraca piksele POZA maską
   f) background_preserve.py - dryf modelu w masce → przywróć oryginał
   g) color_calibrate.py     - zdejmij systematyczny cast koloru (zawsze)
   h) [opcjonalnie, preset Maks] refine pass: encode→denoise 0.18→decode
                               → VaeDriftMatch → BackgroundPreserve
   i) seamless_tone.py ×2     - dopasowanie tonu przy szwie (full + chroma)
   j) grain_transfer.py       - ciągłość ziarna fotograficznego
   k) pad_to_document.py      - rozszerz wynik do rozmiaru dokumentu z alfą
   ↓
4. save_image_rgba.py - zapisuje wynik PNG z kanałem alfa
   ↓
5. panel.js importuje jako nową warstwę w Photoshopie
```

> **Presety jakości** (selektor w panelu) przełączają tylko źródło `SeamlessTone`
> kluczem mappingu `refineSource`: Szybki/Dobra jakość czytają bazę (węzeł 93,
> refine pominięty — ~33% szybciej), Maks czyta wynik refine (węzeł 89).
> `ColorCalibrate` jest odsprzęgnięty i działa w każdym presecie.
>
> **Dlaczego ten łańcuch (kluczowe lekcje, wszystkie mierzone):**
> - Globalny Reinhard (`AreaMatch`+`ColorHarmonize`) **pogarszał** szew → zastąpiony
>   `SeamlessTone` (dyfuzja tonu LF): jasność wnętrza 0.293→0.260, szew −26%.
> - Korekta tonu na całym wnętrzu **zabijała intencję** (zielone włosy→beż) →
>   `interior_strength`+`seam_band` (pełna korekta tylko przy szwie).
> - Plamy tonalne w masce → `BackgroundPreserve` (rozkład zmian bimodalny:
>   dryf <0.05 przywróć, intencja >0.15 zachowaj); dryf tła 0.064→0.006.
> - Duch usuwanych obiektów → `GrainTransfer` tłumi krawędzie, `MaskEdgeRefine`
>   prowadzony obrazem generowanym.
> - Upscale małych wycinków NIE pomaga na Flux2 Klein → guard-rail (Faza D).
>
> **Pomysł użytkownika** (kalibracja barwna) zrealizowany jako `ColorCalibrate`:
> fit afiniczny dryfu na pikselach, które miały zostać niezmienione, i inwersja
> na całości — zdejmuje cast z intencji bez cofania zmiany semantycznej.
>
> **Uwaga o węzłach.** Powyżej jest *aktywny* łańcuch z `inpainting-api.json`.
> Pozostałe węzły RasterRelay (`area_match`, `color_harmonize`, `color_match`,
> `grain_transfer`, `edge_harmonize`, `background_preserve`, `selection_mask`,
> warianty SmartCrop/GrainInjector z `match_and_align.py`) są **dostępne w
> bibliotece**, ale nie są wpięte w domyślny workflow — celowe zaplecze do
> dalszej pracy (np. transfer ziarna jako kolejny etap po SeamlessTone).

## Zarządzanie Pamięcią GPU

Każdy node powinien zwalniać pamięć po dużych operacjach:

```python
def process(self, image, mask, ...):
    # ... operacje na tensorach ...
    
    # Zwolnij pamięć
    del temp_tensor1, temp_tensor2
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    
    return (result,)
```

## Walidacja Danych

Wszystkie nodes walidują dane wejściowe:

```python
def process(self, image, mask, crop_width, crop_height, ...):
    # Walidacja wymiarów
    if crop_width <= 0 or crop_height <= 0:
        raise ValueError(f"Dimensions must be positive, got {crop_width}x{crop_height}")
    
    if crop_width > 16384 or crop_height > 16384:
        raise ValueError(f"Dimensions too large (max 16384)")
    
    # Walidacja bounds
    if crop_left + crop_width > doc_width:
        raise ValueError("Crop region exceeds document bounds")
```

## Testowanie

### Testy Jednostkowe

Każdy node ma testy w `comfy_nodes/tests/`:

```python
def test_color_harmonize_basic():
    harmonizer = RasterRelayColorHarmonize()
    
    original = torch.rand((1, 100, 100, 3))
    generated = torch.rand((1, 100, 100, 3))
    mask = torch.ones((1, 100, 100))
    
    (result,) = harmonizer.harmonize(original, generated, mask, ...)
    
    assert result.shape == (1, 100, 100, 3)
    assert result.min() >= 0.0
    assert result.max() <= 1.0
```

### Uruchamianie Testów

```bash
# Wszystkie testy Python
cd comfy_nodes
python -m pytest tests/

# Pojedynczy test
python tests/color_harmonize_test.py

# Testy JavaScript
cd photoshop_plugin
node tests/panel-helpers.test.js
```

## Rozszerzanie Projektu

### Dodawanie Nowego Node

1. Utwórz `comfy_nodes/nodes/your_node.py`
2. Zaimplementuj klasę z wymaganymi atrybutami
3. Dodaj testy w `comfy_nodes/tests/your_node_test.py`
4. Zarejestruj w `comfy_nodes/__init__.py`
5. Użyj wspólnych funkcji z `utils/mask_processing.py`

### Dodawanie Nowego Testu

1. Utwórz plik `your_feature_test.py`
2. Użyj standardowego formatu testów
3. Testuj przypadki brzegowe (edge cases)
4. Testuj obsługę błędów

### Modyfikacja Istniejącego Node

1. Zmodyfikuj implementację
2. Zaktualizuj testy
3. Uruchom wszystkie testy
4. Zaktualizuj CHANGELOG.md

## Wersjonowanie

Projekt używa [Semantic Versioning](https://semver.org/):
- **MAJOR** (X.0.0) - niekompatybilne zmiany API
- **MINOR** (0.X.0) - nowa funkcjonalność (wstecznie kompatybilna)
- **PATCH** (0.0.X) - naprawy błędów

## Zasoby

- [ComfyUI Documentation](https://github.com/comfyanonymous/ComfyUI)
- [Photoshop UXP API](https://developer.adobe.com/photoshop/uxp/)
- [Tauri Documentation](https://tauri.app/)
- [PyTorch Documentation](https://pytorch.org/docs/)

---

**Wersja dokumentacji:** 1.0.0 (2026-06-11)
**Ostatnia aktualizacja:** 2026-06-11
