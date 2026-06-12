# Raport sesji — RasterRelay (2026-06-11/12)

Raport zmian przeprowadzonych podczas sesji rozwojowej. Punkt wyjścia:
chaotyczna baza z wieloma błędami i niespójnym wynikiem inpaintingu. Stan
końcowy: dopracowany, mierzony, produkcyjny pipeline z UX i dokumentacją.

**Zakres liczbowo:** 17 commitów, 145 plików, **+8221 / −1588** linii,
10 nowych węzłów ComfyUI, 73 testy Pythona + 32 JS (zielone).
Gałąź robocza `cleanup/2026-06-11` → scalona do `main` (`70f1f0d`).

---

## 1. Główny problem i jak go rozwiązaliśmy

**Problem:** wygenerowany fragment wyróżniał się jasnością/kolorem od reszty
zdjęcia — całość nie była spójna.

**Diagnoza (mierzona, nie „na oko"):** na realnym zdjęciu generowany obszar był
~+0.03 jaśniejszy od otoczenia, a istniejący łańcuch `AreaMatch + ColorHarmonize`
(globalny Reinhard) **pogarszał** szew (ΔL 0.0207 → 0.0223), zamiast go naprawiać.

**Rozwiązanie:** zbudowany od zera, wielostopniowy łańcuch deterministyczny,
gdzie każdy węzeł ma jedną jasną odpowiedzialność.

### Fazy A–D

| Faza | Co dodała | Wynik (mierzony) |
|------|-----------|------------------|
| **A** — DifferentialDiffusion | gradient siły denoise z miękkiej maski | szew −22%; `InpaintModelConditioning` odrzucony (piksel-w-piksel bez efektu na Klein GGUF) |
| **B** — refine pass + ColorCalibrate | drugi przebieg niskim denoise + kalibracja barwna | roztapia granice wewnętrzne; cast zdjęty z intencji |
| **C** — finisher | MaskEdgeRefine + chroma + GrainTransfer | szew na poziomie kosmyków, ciągłość ziarna |
| **D** — guard-rail rozdzielczości | generacja w optymalnej rozdzielczości | duże zdjęcia bezpieczne; test 2.79 MP: szew **0.0012** |

**Kluczowy węzeł — `SeamlessTone`:** zamiast jednej globalnej średniej,
dyfunduje ton otoczenia do wnętrza maski i przesuwa tylko niską częstotliwość
generacji. Naprawia offset **i gradienty światła**, zachowując detal.
Zmierzone end-to-end: jasność wnętrza 0.293 → 0.260 (cel 0.262), szew −26%.

## 2. Hotfixy po realnych testach użytkownika

Każdy zgłoszony przez użytkownika problem zdiagnozowany etap-po-etapie:

1. **Zielone włosy wyszły beżowe** — korekta tonu działała na całym wnętrzu
   maski i zabijała intencję. Fix: korekta ważona pasmem szwu
   (`interior_strength` + `seam_band`) — pełna tylko przy granicy.
   Zieleń zachowana (+0.066 raw → +0.037).
2. **Plamy tonalne w kształcie maski** (ramię, ściana) — niezamierzony dryf
   modelu nie był korygowany. Fix: `BackgroundPreserve` w łańcuchu (rozkład
   zmian bimodalny: dryf <0.05 przywróć, intencja >0.15 zachowaj).
   Dryf tła 0.064 → 0.006 (**11×**).
3. **Duchy usuwanych obiektów** — `GrainTransfer` wstrzykiwał krawędzie obiektu;
   `MaskEdgeRefine` przyklejał maskę do usuwanego obiektu. Fix: tłumienie
   krawędzi w ziarnie + przewodnik = obraz wygenerowany.

## 3. Pomysł użytkownika → węzeł `ColorCalibrate`

Użytkownik zaproponował: brać obraz wejściowy za referencję i sprowadzać kolory
wyniku do niej. Zrealizowane z ulepszeniem chroniącym intencję: fit afiniczny
przekłamania koloru **tylko na pikselach, które miały zostać niezmienione**,
i inwersja na całości — zdejmuje systematyczny cast modelu także z obszaru
edycji, **bez cofania zmiany semantycznej** (afiniczność nie odwróci brąz→zieleń).

## 4. Tier 1 — UX i wydajność

- **Presety jakości** (Szybki / Dobra jakość / Maks) — przełączają gałąź refine
  jednym połączeniem (`refineSource`); ComfyUI przycina nieużywaną gałąź →
  **24 s vs 36 s** (~33% szybciej) bez utraty jakości.
- **Pasek postępu** przez WebSocket ComfyUI (schemat potwierdzony przez context7).
- **Czytelne błędy** — klasyfikacja (offline / brak modelu / OOM VRAM) z podpowiedzią.

## 5. Tier 2 — produkt i DX

- **Tryb „Usuwanie obiektu"** — szersza maska (+20 px) + niższy próg
  `BackgroundPreserve` (0.10 → 0.04). „Duch" usuwanego obiektu 0.988 → 0.898.
- **`scripts/reload-rasterrelay-nodes.ps1`** — reinstall + restart + sprawdzenie
  gotowości jednym poleceniem (auto-detekcja Pythona).

## 6. Tier 3 — porządki i dokumentacja

- Usunięto duplikat `GrainInjector` (18 → 17 węzłów); 8 węzłów biblioteki
  oznaczonych `(biblioteka)` w menu ComfyUI.
- Przepisany `comfy_nodes/README.md` (podział aktywne/biblioteka).
- Przewodnik użytkownika `docs/uzytkowanie.md` (linkowany z README).

## 7. Nowe węzły ComfyUI (10)

| Węzeł | Status | Rola |
|-------|--------|------|
| `SeamlessTone` | aktywny | bezszwowy ton (dyfuzja LF, full + chroma) |
| `BackgroundPreserve` | aktywny | dryf w masce → oryginał, intencja → generacja |
| `ColorCalibrate` | aktywny | inwersja castu koloru (pomysł użytkownika) |
| `MaskEdgeRefine` | aktywny | maska klei się do krawędzi (guided filter) |
| `GrainTransfer` | aktywny | ciągłość ziarna (tłumi krawędzie) |
| `AreaMatch`, `ColorHarmonize`, `ColorMatch`, `EdgeHarmonize`, `MaskCropper` | biblioteka | wcześniejsze podejścia / pomocniki |

## 8. Aktywny łańcuch (stan końcowy)

```text
gen(DifferentialDiffusion) → VAEDecode → [skala→natywna]
  → MaskEdgeRefine → VaeDriftMatch → BackgroundPreserve → ColorCalibrate
  → [opcjonalny refine pass: preset Maks]
  → SeamlessTone(full) → SeamlessTone(chroma) → GrainTransfer
  → PadToDocument → SaveImage
```

41 węzłów, mapping 28 kluczy, plugin w pełni sterowany mappingiem.

## 9. Walidacja praktyczna

Bateria 6 testów na różnych obrazach (recolor, materiał, wstawienie, usuwanie):
**6/6 PASS**, wyciek poza maskę ≤ 2e-05 wszędzie, szwy 0.007–0.057,
najlepszy przypadek (wstawienie koła off-road) — intencja 0.174, szew niewidoczny.

## 10. Kluczowe lekcje inżynierskie

- **Globalny Reinhard nie radzi sobie z gradientem światła** — dyfuzja tonu LF tak.
- **Korekta koloru nie może działać na całym wnętrzu maski** — zabija intencję.
- **Rozkład zmian w masce jest bimodalny** (dryf vs intencja) — to pozwala
  rozróżnić jedno od drugiego automatycznie.
- **Upscale małych wycinków nie pomaga na Flux2 Klein** — lore z SDXL się nie przenosi.
- **Każdą zmianę walidować pomiarem na żywym ComfyUI**, nie „na oko".

## 11. Co zostało

- **Test 41-węzłowego buildu w prawdziwym Photoshopie** z nowym UI (po stronie użytkownika).
- Przycisk reload w Launcherze (nakładka na gotowy skrypt — wymaga przebudowy Tauri).
- Pomysły na przyszłość: warianty A/B w panelu, iteracyjny re-edit, UI LoRA.

---

## Spis commitów sesji

```
e72d141 cleanup: rejestracja BackgroundPreserve + naprawa ARCHITECTURE.md
a527ef5 feat: SeamlessTone node solves inpaint colour/brightness mismatch
da2871e feat(phase-A): DifferentialDiffusion in production inpaint workflow
107a77f feat(phase-C): deterministic finisher - edge-aware mask, chroma pass, grain
16e8a54 fix: intent-preserving colour chain + ghost-free object removal
7f388bd fix: mask-shaped tone stains - BackgroundPreserve in production chain
3194562 feat(phase-B): refine pass + colour-response calibration (user's idea)
ed1fd83 feat(phase-D): generation-resolution guard-rail (crop-engine)
d1e7459 test: parameterized practical inpainting test driver
4421c13 feat(tier-1): quality presets, progress bar, clear errors
cbef0b3 docs: final pipeline diagram + node inventory in ARCHITECTURE.md
70f1f0d merge: RasterRelay quality pipeline + UX (→ main)
2356a93 feat(tier-2.1): one-command node reload script
e6a1b2d feat(tier-2.2): object-removal mode
8694fdd refactor(tier-3.1): remove duplicate GrainInjector, label library nodes
497f049 docs(tier-3.2): user guide (docs/uzytkowanie.md)
```

*Raport wygenerowany na podstawie historii git (`0789897..HEAD`).*
