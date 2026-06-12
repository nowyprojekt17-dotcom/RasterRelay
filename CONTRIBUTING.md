# Contributing to RasterRelay

Dziękujemy za zainteresowanie contributes do RasterRelay! Ten dokument zawiera wytyczne jak skutecznie contributesować do projektu.

## Struktura Projektu

```
RasterRelay/
├── comfy_nodes/           # Nodes ComfyUI (Python)
│   ├── nodes/             # Implementacje nodes
│   ├── server/            # API endpoints
│   ├── utils/             # Wspólne funkcje
│   └── tests/             # Testy jednostkowe
├── photoshop_plugin/      # Plugin Photoshop (JavaScript)
│   ├── src/               # Kod źródłowy
│   ├── workflows/         # Workflow JSON
│   ├── tests/             # Testy
│   └── test_assets/       # Zasoby testowe
├── launcher/              # Launcher aplikacji (Tauri)
│   ├── src/               # Frontend TypeScript/React
│   └── src-tauri/         # Backend Rust
├── tests/                 # Testy ręczne i skrypty testowe
│   ├── *.py               # Skrypty testowe
│   └── manual/            # Testy ręczne
│       ├── test-images/   # Obrazy testowe
│       └── test-results/  # Wyniki testów
├── scripts/               # Skrypty PowerShell/Bash
├── docs/                  # Dokumentacja
└── workflows/             # Workflow JSON
```

## Konwencje Kodowania

### Python (ComfyUI Nodes)
- **Styl nazewnictwa:** snake_case dla zmiennych i funkcji
- **Formatowanie:** PEP 8
- **Dokumentacja:** Docstrings w formacie Google
- **Typowanie:** Używaj type hints tam gdzie to możliwe

### JavaScript (Photoshop Plugin)
- **Styl nazewnictwa:** camelCase dla zmiennych i funkcji
- **Formatowanie:** 2 spacje wcięcia
- **Quote:** Single quotes dla stringów

### TypeScript/Rust (Launcher)
- **TypeScript:** camelCase, Prettier formatting
- **Rust:** snake_case, standard Rustfmt

## Dodawanie Nowych Nodes

1. Utwórz nowy plik w `comfy_nodes/nodes/`
2. Zaimplementuj klasę z wymaganymi atrybutami:
   ```python
   class RasterRelayYourNode:
       CATEGORY = "RasterRelay"
       RETURN_TYPES = ("IMAGE",)
       RETURN_NAMES = ("image",)
       FUNCTION = "process"
       DESCRIPTION = "Opis tego co node robi."
   ```
3. Dodaj testy jednostkowe w `comfy_nodes/tests/`
4. Zarejestruj node w `comfy_nodes/__init__.py`
5. Użyj wspólnych funkcji z `comfy_nodes/utils/` gdy to możliwe

## Dodawanie Testów

1. Utwórz plik `your_feature_test.py` w odpowiednim katalogu `tests/`
2. Użyj standardowego formatu:
   ```python
   def test_your_feature():
       # Setup
       # Action
       # Assert
   ```
3. Uruchom testy: `python comfy_nodes/tests/your_feature_test.py`

## Zarządzanie Pamięcią GPU

Przy pracy z dużymi tensorami zawsze zwalniaj pamięć:
```python
# Po dużych operacjach
del large_tensor1, large_tensor2
if torch.cuda.is_available():
    torch.cuda.empty_cache()
```

## Walidacja Danych

Zawsze waliduj dane wejściowe:
```python
if dimension <= 0:
    raise ValueError(f"Dimension must be positive, got {dimension}")
if dimension > 16384:
    raise ValueError(f"Dimension too large (max 16384), got {dimension}")
```

## Commit Messages

Używaj konwencjonalnych commit messages:
- `feat:` - Nowa funkcjonalność
- `fix:` - Naprawa błędu
- `docs:` - Zmiany w dokumentacji
- `refactor:` - Refaktoryzacja kodu
- `test:` - Dodanie testów
- `chore:` - Zadania konserwacyjne

Przykład:
```
feat: add edge_harmonize node for halo removal

Implements color transition smoothing at mask edges to eliminate
visible halos between generated and original images.

Closes #42
```

## Pull Request Process

1. Fork repozytorium
2. Utwórz branch dla swojej funkcjonalności: `git checkout -b feature/amazing-feature`
3. Commituj zmiany: `git commit -m 'feat: add amazing feature'`
4. Push do branch: `git push origin feature/amazing-feature`
5. Otwórz Pull Request

### Checklist PR

- [ ] Kod jest zgodny z konwencjami projektu
- [ ] Dodano testy jednostkowe
- [ ] Wszystkie testy przechodzą
- [ ] Zaktualizowano dokumentację
- [ ] Dodano wpis w CHANGELOG.md
- [ ] Kod jest sformatowany i nie zawiera zbędnych zmian

## Uruchamianie Testów

```bash
# Wszystkie testy Python
python comfy_nodes/tests/match_and_align_test.py
python comfy_nodes/tests/color_harmonize_test.py
python comfy_nodes/tests/grain_transfer_test.py
python comfy_nodes/tests/edge_harmonize_test.py

# Testy JavaScript
cd photoshop_plugin
node tests/panel-helpers.test.js
```

## Pytania?

Jeśli masz pytania, otwórz issue na GitHubie z etykietą `question`.

---

Dziękujemy za helps w rozwoju RasterRelay! 🎨
