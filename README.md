# RasterRelay

RasterRelay to projekt narzędzia do Photoshopa, które ma łączyć pracę z obrazem z lokalnym ComfyUI.

Pierwszy etap nie buduje jeszcze całej wtyczki. Zaczynamy od małego Launchera, czyli aplikacji pomocniczej, która sprawdzi, czy lokalne środowisko ComfyUI jest gotowe do pracy.

## Co jest teraz najważniejsze

- uporządkowana struktura repozytorium,
- prosty Launcher z ekranem Readiness,
- wykrywanie folderu ComfyUI,
- ręczne wskazanie folderu ComfyUI, jeśli autoskan go nie znajdzie,
- widoczna sekcja LoRA od samego początku,
- miejsce na przyszły workflow inpaintingu,
- miejsce na przyszłe custom nodes RasterRelay.

## Struktura projektu

- `assets/brand/` - logo i materiały marki RasterRelay.
- `launcher/` - aplikacja Launcher oparta o Tauri, React i Vite.
- `docs/` - proste notatki projektowe i instrukcje.
- `workflows/inpainting/` - miejsce na przyszły workflow inpaintingu z obsługą LoRA.
- `comfy_nodes/` - miejsce na przyszłe własne custom nodes dla ComfyUI.

## Jak uruchomić Launcher

Launcher potrzebuje Node.js, npm oraz Rust/Cargo.

Na tym komputerze Node.js i npm są już dostępne. Rust/Cargo trzeba jeszcze zainstalować, jeśli komenda `cargo --version` nie działa.

Po przygotowaniu narzędzi:

```powershell
cd C:\Users\Mierz\Desktop\RasterRelay\launcher
npm install
npm run tauri dev
```

Jeśli Launcher nie znajdzie ComfyUI sam, kliknij `Wybierz folder ComfyUI` i wskaż główny folder ComfyUI. To musi być folder z plikiem `main.py`.

Jeśli chcesz tylko sprawdzić ekran UI w przeglądarce, bez okna Tauri:

```powershell
cd C:\Users\Mierz\Desktop\RasterRelay\launcher
npm install
npm run dev
```

## Ważna zasada

LoRA nie są dodatkiem doklejonym później. RasterRelay od początku traktuje LoRA jako ważną część systemu generowania.
