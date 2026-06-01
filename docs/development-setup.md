# Przygotowanie środowiska

RasterRelay Launcher używa Tauri, React i Vite.

Prosto mówiąc:

- Tauri robi okno aplikacji desktopowej.
- React pomaga budować ekran z małych elementów.
- Vite pomaga szybko uruchamiać i budować ekran.
- Oficjalny plugin dialog Tauri otwiera okno wyboru folderów i plików.

## Wymagane narzędzia

- Node.js
- npm
- Rust/Cargo

Sprawdzenie:

```powershell
node --version
npm --version
cargo --version
```

Jeżeli `cargo --version` nie działa, trzeba zainstalować Rust przez Rustup.

## Uruchomienie UI w przeglądarce

```powershell
cd C:\Users\Mierz\Desktop\RasterRelay\launcher
npm install
npm run dev
```

Ten tryb jest dobry do oglądania ekranu. Nie ma wtedy dostępu do prawdziwych komend Tauri, więc skan dysku i start ComfyUI działają dopiero w aplikacji Tauri.

## Uruchomienie jako aplikacja Tauri

```powershell
cd C:\Users\Mierz\Desktop\RasterRelay\launcher
npm install
npm run tauri dev
```

Jeżeli Tauri zgłosi brak Rust/Cargo, najpierw trzeba dokończyć instalację Rusta.

## Ręczne wskazanie ComfyUI

W oknie Tauri kliknij `Wybierz folder ComfyUI`.

Wskaż folder, który zawiera `main.py`. Jeżeli wybierzesz folder z samymi workflow albo innymi plikami, Launcher pokaże błąd i niczego nie zapisze.

## Start ComfyUI z Launchera

Po wybraniu poprawnego folderu kliknij `Start ComfyUI`.

Launcher szuka Pythona w tej kolejności:

- `ComfyUI/venv/Scripts/python.exe`,
- `ComfyUI/python_embeded/python.exe`,
- `ComfyUI/python_embedded/python.exe`,
- `../python_embeded/python.exe`, czyli portable Python obok folderu `ComfyUI`,
- `../python_embedded/python.exe`,
- systemowy `python` z PATH.

ComfyUI powinno odpowiadać pod adresem `http://127.0.0.1:8188`.

Przycisk `Stop` zatrzymuje tylko ComfyUI uruchomione przez Launcher. Jeśli ComfyUI działało już wcześniej, Launcher pokaże status, ale nie będzie zamykał cudzego procesu.

## Skrót na pulpicie

Po zbudowaniu Launchera możesz utworzyć skrót na pulpicie:

```powershell
cd C:\Users\Mierz\Desktop\RasterRelay
.\scripts\create-desktop-shortcut.ps1
```

Skrypt nie instaluje niczego w systemie. Tworzy tylko plik `.lnk`, który wskazuje na aktualny plik `rasterrelay-launcher.exe` z folderu debug.
