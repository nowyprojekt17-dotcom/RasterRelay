# Changelog

Wszystkie znaczące zmiany w tym projekcie będą dokumentowane w tym pliku.

Format bazuje na [Keep a Changelog](https://keepachangelog.com/pl/1.0.0/),
a ten projekt adheres to [Semantic Versioning](https://semver.org/lang/pl/).

## [Unreleased]

> 📋 Pełny narracyjny raport tej sesji (problem koloru, Fazy A–D, hotfixy,
> Tier 1–3, metryki, lekcje): [`docs/raport-sesji-2026-06-12.md`](docs/raport-sesji-2026-06-12.md).

### Fixed (Launcher / Photoshop)
- **Pixel-audyt koloru w Photoshopie**: `imaging.getPixels()` wymaga modal scope,
  więc snapshot przed/po kompozycji jest teraz pobierany przez `executeAsModal`
  (`RasterRelay Pixel Audit Snapshot`). Bez tego wtyczka pobierała wynik z
  ComfyUI, ale odmawiała wstawienia warstwy: „The requested functionality is only
  allowed from inside a modal scope".
- **Start ComfyUI z terminalem**: release launcher działa jako aplikacja GUI bez
  własnej konsoli (`windows_subsystem = "windows"`), więc `CREATE_NEW_CONSOLE` +
  `Stdio::inherit()` dawało puste/znikające okno. Ścieżka terminalowa uruchamia
  teraz ComfyUI przez `cmd /K`, które posiada nową konsolę i utrzymuje ją otwartą;
  zwykły start bez terminala pozostaje ukryty.

### Changed (Tier 4 — pomiarowe uproszczenie łańcucha koloru)
- **Łańcuch koloru skrócony 42 → 30 węzłów** na podstawie A/B (5 przypadków
  krytycznych kolorystycznie, `scripts/run-practical-color-lock-suite-with-comfy.py`).
  Nowy graf: `MaskEdgeRefine → VaeDriftMatch → ColorCalibrate →
  SeamlessTone(full, seam-band) → ReferenceColorLock → PadToDocument`.
- **Usunięte (zmierzony zerowy wkład):** `BackgroundPreserve`,
  drugi `SeamlessTone(chroma)`, `GrainTransfer` oraz martwa, niepodłączona
  („orphan") gałąź refine pass (węzły 17,18,70,71,72,73,74,88,89 — policzone,
  nieosiągalne od `SaveImage`). Z tymi węzłami i bez nich: out-of-mask=0,
  błąd hue/chroma w masce=0, delta szwu (excess vs źródło) równa lub niższa
  bez nich (np. gta-badge −5.1 → −6.2; desk-can +0.97 → −1.9).
- **`ReferenceColorLock` zostaje** — wariant minimalny (bez niego) rozjeżdżał
  paletę: błąd chroma do **259**, hue do **173°** (z nim: 0/0). To on, a nie
  GrainTransfer, jest nośnikiem locka palety.
- **Jedna robocza rozdzielczość generacji** (14/15/21/62 = node 16): koniec
  mieszanki 1024² (generacja) vs 1024×768 (skala/crop) i dystorsji proporcji;
  węzły koloru/szwu dostają oba obrazy w tym samym rozmiarze.
- **ICC kierunek „na zewnątrz"** (`panel.js`): konwersja eksportowej kopii do
  sRGB została zdegradowana do bezpiecznego no-opu, bo Photoshop Beta potrafi
  zgłosić „Konwersja do profilu nie jest aktualnie dostępna" jako modalny błąd
  mimo `batchPlay`. Nie blokujemy generacji dla tej best-effort osłony; właściwe
  domknięcie profilu robi tag sRGB iCCP na wynikowym PNG + fallback placementu.
- **ICC kierunek „do środka"** — domknięty. `RasterRelaySaveImage` osadza teraz
  w PNG tag sRGB (chunk iCCP, profil z `PIL.ImageCms`), więc Photoshop konwertuje
  wynik do przestrzeni dokumentu wide-gamut zamiast błędnie interpretować
  nietagowany RGB jako profil dokumentu. **Tylko oznaczenie — piksele bez zmian.**
  Belt-and-suspenders w `placeImageFileAsLayer`: odczyt profilu dokumentu (log do
  metadanych placement/joba) i fallback — dla dokumentu nie-sRGB wymuszenie sRGB
  na wstawionym smart obiekcie (po `placeEvent`), w pełni izolowany (nigdy nie
  rzuca, zawsze wraca do dokumentu źródłowego). Ścieżka sRGB pozostaje no-opem.
  Zweryfikowane end-to-end: realny wynik ComfyUI ma chunk iCCP (588 B „sRGB"),
  RGBA i alfę 0/255. Nowy test: `save_image_rgba_test.py`
  (`test_saved_png_is_tagged_srgb_and_preserves_alpha`).
- **Presety jakości** różnią się już tylko liczbą kroków (8/14/20); usunięto
  nieistniejący „refine" z etykiet i logiki (`panel-helpers.js`).
- **Pomiar:** `audit-color-lock-workflow.py` raportuje teraz deltę szwu
  (`seam_*`, ring wewnątrz vs na zewnątrz granicy maski, nadwyżka vs źródło)
  i średnią różnicę w masce; nowe flagi `--workflow` i `--measure-only`
  umożliwiają A/B wielu workflowów w jednym bootcie ComfyUI.

### Added (Tier 3 — porządki i dokumentacja)
- Usunięto duplikat węzła `RasterRelayGrainInjector` (18 → 17 węzłów); 8 węzłów
  biblioteki oznaczonych `(biblioteka)` w nazwach menu ComfyUI.
- Przepisany `comfy_nodes/README.md` (podział aktywne/biblioteka + kolejność).
- Przewodnik użytkownika `docs/uzytkowanie.md` (linkowany z README).

### Added (Tier 2 — produkt/DX)
- **Tryb „Usuwanie obiektu"** (selektor w panelu): poszerza maskę generacji
  o +20 px (obiekt znika bez obwódki) i obniża próg `BackgroundPreserve`
  (0.10→0.04), żeby usunięcie nie było cofane, gdy nowe tło przypomina
  otoczenie. Zmierzone: „duch" usuwanego obiektu 0.988→0.898 (mniejszy wkład
  kompozycji w ghosting). `backgroundPreserveThreshold` celuje teraz w oba
  węzły BgPreserve (95 + 89).
- **`scripts/reload-rasterrelay-nodes.ps1`** — jedno polecenie: reinstall
  węzłów + restart ComfyUI + sprawdzenie gotowości (auto-detekcja Pythona).

### Added (Tier 1 — UX/wydajność)
- **Presety jakości w panelu (widoczny selektor):** Szybki (8 kroków, bez
  refine), Dobra jakość (14, bez refine, domyślny), Maks (20, z refine).
  Preset przełącza źródło `SeamlessTone` między bazą (węzeł 93) a wynikiem
  refine (węzeł 89) przez klucz mappingu `refineSource`; ComfyUI przycina
  gałąź refine gdy nieużywana → Szybki/Zbalansowany ~33% szybsze (zmierzone:
  24 s vs 36 s). ColorCalibrate odsprzęgnięty od refine — działa zawsze.
- **Pasek postępu generacji** przez WebSocket ComfyUI (`/ws`,
  progress/executing); best-effort, polling pozostaje źródłem ukończenia.
- **Czytelne błędy:** klasyfikacja (ComfyUI offline / brak modelu-węzłów /
  OOM VRAM) z konkretną podpowiedzią naprawy w panelu.

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
