# RasterRelay

RasterRelay to projekt narzędzia do Photoshopa, które ma łączyć pracę z obrazem z lokalnym ComfyUI.

Docelowa wersja Photoshopa dla tego projektu to **Photoshop Beta 27.8**.

> 📖 **Jak używać wtyczki krok po kroku:** [`docs/uzytkowanie.md`](docs/uzytkowanie.md)
> (zaznaczenie → tryb → jakość → prompt → warstwa, presety, usuwanie, typowe problemy).

Pierwsze etapy nie budują jeszcze całej wtyczki. Zaczynamy od małego Launchera, czyli aplikacji pomocniczej, która sprawdza lokalne środowisko ComfyUI i pomaga je przygotować.

## Co jest teraz najważniejsze

- uporządkowana struktura repozytorium,
- prosty Launcher z ekranem Readiness,
- wykrywanie folderu ComfyUI,
- ręczne wskazanie folderu ComfyUI, jeśli autoskan go nie znajdzie,
- uruchamianie i zatrzymywanie lokalnego ComfyUI z Launchera,
- sprawdzanie, czy workflow API dla Photoshopa jest gotowy,
- widoczna sekcja LoRA od samego początku,
- bezpieczne dodawanie plików LoRA i GGUF,
- miejsce na przyszły workflow inpaintingu,
- miejsce na przyszłe custom nodes RasterRelay.

## Struktura projektu

- `assets/brand/` - logo i materiały marki RasterRelay.
- `launcher/` - aplikacja Launcher oparta o Tauri, React i Vite.
- `photoshop_plugin/` - pierwszy panel UXP dla Photoshopa.
- `docs/` - proste notatki projektowe i instrukcje.
- `workflows/inpainting/` - miejsce na przyszły workflow inpaintingu z obsługą LoRA.
- `comfy_nodes/` - miejsce na przyszłe własne custom nodes dla ComfyUI.

## Jak uruchomić Launcher

Launcher potrzebuje Node.js, npm oraz Rust/Cargo.

Po przygotowaniu narzędzi:

```powershell
cd C:\Users\Mierz\Desktop\RasterRelay\launcher
npm install
npm run tauri dev
```

Jeżeli Launcher nie znajdzie ComfyUI sam, kliknij `Wybierz folder ComfyUI` i wskaż główny folder ComfyUI. To musi być folder z plikiem `main.py`.

Po wskazaniu poprawnego folderu możesz użyć `Start ComfyUI`. Launcher uruchamia ComfyUI lokalnie pod adresem `http://127.0.0.1:8188`.

Przycisk `Stop` zatrzymuje tylko proces uruchomiony przez Launcher. Jeśli ComfyUI było odpalone wcześniej ręcznie, Launcher pokaże status, ale nie zamknie go na siłę.

Launcher ma też panel `Photoshop Beta 27.8`. Jeśli Photoshop Beta jest zainstalowany w standardowej ścieżce Adobe, przycisk `Start Photoshop` uruchamia:

```text
C:\Program Files\Adobe\Adobe Photoshop (Beta)\Photoshop.exe
```

## Skrót na pulpicie

Po zbudowaniu wersji debug możesz utworzyć ikonę na pulpicie:

```powershell
cd C:\Users\Mierz\Desktop\RasterRelay
.\scripts\create-desktop-shortcut.ps1
```

Skrót prowadzi do `launcher\src-tauri\target\debug\rasterrelay-launcher.exe`.

Jeśli chcesz tylko sprawdzić ekran UI w przeglądarce, bez okna Tauri:

```powershell
cd C:\Users\Mierz\Desktop\RasterRelay\launcher
npm install
npm run dev
```

## Ważna zasada

LoRA nie są dodatkiem doklejonym później. RasterRelay od początku traktuje LoRA jako ważną część systemu generowania.

## Etap 3

Launcher potrafi już bezpiecznie dodać plik LoRA albo GGUF:

- LoRA trafia do `ComfyUI/models/loras`.
- GGUF trafia do `ComfyUI/models/unet`, bo lokalny loader `UnetLoaderGGUF` widzi tam model `flux-2-klein-9b-Q4_K_M.gguf`.
- Launcher najpierw sprawdza plik i pokazuje panel potwierdzenia.
- Launcher nie nadpisuje istniejących plików.

## Etap 4

Launcher zaczyna aktywować ComfyUI:

- sprawdza, czy lokalne API ComfyUI odpowiada na `http://127.0.0.1:8188`,
- uruchamia `main.py` z wybranego folderu ComfyUI,
- szuka Pythona w `venv`, w portable Python obok folderu `ComfyUI` albo w systemowym `python`,
- pokazuje status uruchomienia w osobnym panelu,
- zatrzymuje tylko ComfyUI uruchomione przez Launcher.

Photoshop, workflow inpaintingu i pełna edycja obrazu są nadal przed nami.

## Photoshop Plugin

Pierwszy szkielet panelu znajduje się w `photoshop_plugin/`.

Panel ma funkcję `Inpainting Brush Tool`, sprawdzanie aktywnego dokumentu, sprawdzanie zaznaczenia i sprawdzanie połączenia z lokalnym ComfyUI. Potrafi też wyeksportować aktywny dokument jako PNG, utworzyć maskę PNG z pikseli zaznaczenia Photoshopa, zapisać paczkę zadania JSON, wysłać obraz oraz maskę do ComfyUI, wysłać workflow do `/prompt`, pobrać wynik z `/history` i `/view`, a potem spróbować wstawić wynik do Photoshopa jako nową warstwę.

Panel umie już zebrać jedną albo kilka LoRA wpisanych przez użytkownika i przekazać je do workflow.

W repo jest już pierwszy prawdziwy `photoshop_plugin/workflows/inpainting-api.json` dla lokalnego ComfyUI:

- model: `flux-2-klein-9b-Q4_K_M.gguf`,
- text encoder: `qwen_3_8b_fp8mixed.safetensors`,
- VAE: `flux2-vae.safetensors`,
- maska: czerwony kanał z pliku maski PNG,
- wynik: obraz z ComfyUI sklejony z oryginałem po masce.

Ten workflow przeszedł test lokalnego ComfyUI przez `/prompt` na małym obrazie kontrolnym. Nadal brakuje testu w Photoshop Beta 27.8 na prawdziwym dokumencie i oceny jakości na większym obrazie.

## Test workflow bez Photoshopa

Przed testem w Photoshopie można sprawdzić sam środek systemu, czyli ComfyUI + workflow:

```powershell
cd C:\Users\Mierz\Desktop\RasterRelay
.\scripts\verify-comfy-workflow.ps1
```

Skrypt tworzy mały obraz i maskę w `E:\AI\ComfyUI\input`, wysyła workflow do lokalnego ComfyUI i czeka na wynik w `E:\AI\ComfyUI\output\RasterRelay`.

Launcher pokazuje osobny status `Workflow API`, żeby było jasne, czy pliki `photoshop_plugin/workflows/inpainting-api.json` i `photoshop_plugin/workflows/inpainting-api.mapping.json` są już gotowe.

W panelu `Workflow API` są też dwa przyciski:

- `Dodaj workflow API` - wybiera prawdziwy eksport API JSON z ComfyUI i zapisuje go jako `photoshop_plugin/workflows/inpainting-api.json`.
- `Dodaj mapping` - wybiera plik opisujący, gdzie w workflow wstawić obraz, maskę i prompt, i zapisuje go jako `photoshop_plugin/workflows/inpainting-api.mapping.json`.

Launcher najpierw sprawdza wybrany plik i pokazuje potwierdzenie. Mapping musi mieć wejścia `sourceImage`, `selectionMask` i `prompt`, inaczej panel Photoshopa nie wiedziałby, gdzie podstawić dane z obrazu.

Gdy ComfyUI działa, Launcher próbuje też sprawdzić `/object_info`, czyli listę dostępnych node'ów. To pomaga zobaczyć, czy lokalne ComfyUI ma podstawowe elementy potrzebne do workflow inpaintingu.

Instrukcja uruchomienia jest w `photoshop_plugin/README.md`.

## Ręczny test końcowy w Photoshopie

1. Uruchom `RasterRelay Launcher` ikoną z pulpitu.
2. Kliknij `Start ComfyUI` i poczekaj, aż status będzie aktywny.
3. W panelu `Photoshop Beta 27.8` kliknij `Start Photoshop`.
4. W Adobe UXP Developer Tool dodaj manifest `photoshop_plugin/manifest.json`, jeśli panel nie jest jeszcze załadowany.
5. W Photoshopie otwórz obraz, zaznacz obszar i otwórz panel `RasterRelay`.
6. Wpisz prompt, zostaw `Dobra jakość`, kliknij `Sprawdź gotowość`.
7. Jeśli gotowość przejdzie, kliknij `Przygotuj edycję`.

Oczekiwany wynik: nowa warstwa z wynikiem ComfyUI oraz maską ograniczającą zmianę do zaznaczenia.
