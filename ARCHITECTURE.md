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
┌─────────────────────────────────────────────────────────────┐
│              ComfyUI Workflow (inpainting-api.json)          │
│                                                              │
│  LoadImage + LoadImageMask                                   │
│        │              │                                      │
│        │              ▼                                      │
│        │        MaskCropper ──▶ VAEEncode ──▶ SetLatentNoise │
│        │                                          │          │
│        │                                          ▼          │
│        │                              SamplerCustomAdvanced  │
│        │                                          │          │
│        │                                          ▼          │
│        │                                      VAEDecode      │
│        │                                          │          │
│        ▼                                          ▼          │
│   (oryginał) ───────────────────────────▶ VaeDriftMatch     │
│                                                   │          │
│                                                   ▼          │
│                                              AreaMatch       │
│                                                   │          │
│                                                   ▼          │
│                                            ColorHarmonize    │
│                                                   │          │
│                                                   ▼          │
│                                            PadToDocument     │
│                                                   │          │
│                                                   ▼          │
│                                       SaveImage (RGBA)       │
└────────────────────────────┼────────────────────────────────┘
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
│   ├── match_and_align.py      # Dopasowanie i wyrównanie
│   ├── color_harmonize.py      # Harmonizacja kolorów
│   ├── color_match.py          # Dopasowanie kolorów
│   ├── grain_transfer.py       # Transfer ziarna
│   ├── edge_harmonize.py       # Harmonizacja krawędzi
│   ├── area_match.py           # Dopasowanie obszaru
│   ├── mask_cropper.py         # Przyycinanie maski
│   ├── background_preserve.py  # Zachowanie tła
│   └── lora_stack.py           # Stos LoRA
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
   a) mask_cropper.py     - przycina maskę dokumentu do obszaru pracy
   b) (VAEEncode + SetLatentNoiseMask + sampler Flux) - generacja
   c) match_and_align.py  - VaeDriftMatch koryguje dryf jasności z VAE
   d) area_match.py       - AreaMatch dopasowuje obszar do otoczenia
   e) color_harmonize.py  - ColorHarmonize harmonizuje kolory po masce
   f) pad_to_document.py  - rozszerza wynik do rozmiaru dokumentu
   ↓
4. save_image_rgba.py - zapisuje wynik PNG z kanałem alfa
   ↓
5. panel.js importuje jako nową warstwę w Photoshopie
```

> **Uwaga o węzłach.** Powyżej jest *aktywny* łańcuch z `inpainting-api.json`.
> Pozostałe węzły RasterRelay (`color_match`, `grain_transfer`,
> `edge_harmonize`, `background_preserve`, `selection_mask`, `lora_stack`,
> warianty SmartCrop/GrainInjector z `match_and_align.py`) są **dostępne w
> bibliotece**, ale nie są jeszcze wpięte w domyślny workflow. To celowe
> zaplecze do dalszej pracy nad spójnością koloru/jasności — nie martwy kod.
> Jedyne znane nakładanie się: `GrainInjector` (w `match_and_align.py`) i
> `GrainTransfer` robią to samo — do ujednolicenia później.

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
