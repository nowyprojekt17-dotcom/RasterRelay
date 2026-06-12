# RasterRelay — przewodnik użytkownika

RasterRelay pozwala edytować **zaznaczony fragment** zdjęcia lokalnym modelem AI
(Flux.2 Klein) i wstawia wynik jako nową warstwę w Photoshopie — bez psucia
jakości reszty obrazu. Idealne do dużych zdjęć: zamiast przerabiać całość,
zmieniasz tylko mały zaznaczony obszar.

---

## 1. Czego potrzebujesz

- **Photoshop Beta 27.8+**
- **ComfyUI** z modelami: `flux-2-klein-9b-Q4_K_M.gguf` (w `models/unet`),
  `qwen_3_8b_fp8mixed.safetensors`, `flux2-vae.safetensors`
- **Węzły RasterRelay** zainstalowane w ComfyUI (`scripts/install-comfy-nodes.ps1`)
- Karta GPU z ~8 GB+ VRAM (testowane na RTX 3090)

## 2. Uruchomienie

1. **Launcher → „Start ComfyUI"** (albo ręcznie `python main.py --listen 127.0.0.1 --port 8188`).
2. W Photoshopie otwórz **UXP Developer Tool** i załaduj `photoshop_plugin/manifest.json`
   (jeśli panel nie jest jeszcze dodany). Panel „RasterRelay" pojawi się w `Wtyczki`.
3. W panelu kliknij **„Sprawdź ComfyUI"** — kropka powinna zaświecić na zielono.

## 3. Edycja krok po kroku

1. Otwórz zdjęcie i **zaznacz** obszar do zmiany (dowolne narzędzie zaznaczania —
   lasso, zaznaczenie obiektu, prostokąt; kształt może być dowolny).
2. W panelu wybierz **Tryb**:
   - **Edycja** — zmieniasz zaznaczony obszar (recolor, podmiana, materiał).
   - **Usuwanie obiektu** — usuwasz to, co zaznaczone; maska zostaje poszerzona,
     żeby obiekt zniknął bez obwódki.
3. Wybierz **Jakość** (patrz niżej).
4. Wpisz **Prompt** — opisz, co ma się pojawić (przy usuwaniu opisz tło, np.
   „czysta ściana, naturalna tekstura").
5. Kliknij **„Przygotuj edycję"**. Pasek postępu pokazuje generację.
6. Wynik wpada jako **nowa warstwa z maską** — oryginał zostaje nietknięty.
   Maskę warstwy możesz dalej ręcznie poprawić w Photoshopie.

## 4. Presety jakości

| Preset | Kroki | Refine | Kiedy używać |
|--------|-------|--------|--------------|
| **Szybki** | 8 | nie | szybkie próby promptów, szkice |
| **Dobra jakość** | 14 | nie | **domyślny** — codzienna praca |
| **Maks** | 20 | tak | trudne szwy, gdy potrzebujesz maksymalnej gładkości |

„Refine" to dodatkowy przebieg ujednolicający — daje najgładszy szew kosztem
~50% dłuższego czasu. W większości przypadków „Dobra jakość" wystarcza.

## 5. Wskazówki do promptów

- Opisuj **co ma być**, nie „zmień". Dobrze: „chromowany grill samochodu,
  fotorealistycznie, to samo oświetlenie".
- Dodawaj kontekst światła/materiału: „naturalne światło studyjne",
  „te same odbicia i cienie" — pomaga wtopić edycję.
- Przy **dużej zmianie koloru** (np. zielone włosy) prompt może być krótki:
  „zielone włosy" — pipeline sam zadba o spójność tonalną z resztą.
- Przy **usuwaniu** opisz, co zostaje: „goła skóra, bez biżuterii",
  „pusty blat, słoje drewna".

## 6. Jak to działa (w skrócie)

Generacja idzie w optymalnej rozdzielczości modelu, a potem deterministyczny
łańcuch dopasowuje wynik do oryginału: przywraca piksele poza maską, zdejmuje
systematyczne przekłamanie koloru modelu, wtapia ton przy szwie i przenosi
ziarno. Dzięki temu wygenerowany fragment **nie wyróżnia się** jasnością ani
kolorem od reszty zdjęcia. Szczegóły w `ARCHITECTURE.md`.

## 7. Typowe problemy

| Komunikat / objaw | Przyczyna | Rozwiązanie |
|-------------------|-----------|-------------|
| „ComfyUI nie odpowiada" | ComfyUI niewłączone | Launcher → Start ComfyUI, potem „Sprawdź ComfyUI" |
| „ComfyUI odrzuciło workflow" | brak modelu lub węzła | sprawdź modele; `scripts/reload-rasterrelay-nodes.ps1` |
| „Zabrakło pamięci GPU (VRAM)" | za duże zaznaczenie | mniejsze zaznaczenie albo preset „Szybki" |
| Wynik się nie wkleił jako warstwa | błąd wstawiania | pliki wyniku są zapisane; sprawdź komunikat w panelu |
| Edycja „nie złapała" / zostały resztki | maska minęła obiekt | zaznacz dokładniej; przy usuwaniu użyj trybu „Usuwanie obiektu" |
| Generacja długo trwa | preset „Maks" (refine) | użyj „Dobra jakość" lub „Szybki" |

## 8. Po zmianie węzłów (dla deweloperów)

Węzły instalują się jako **kopia** — po edycji `comfy_nodes/` uruchom:

```powershell
.\scripts\reload-rasterrelay-nodes.ps1
```

(reinstall + restart ComfyUI + sprawdzenie gotowości jednym poleceniem).
