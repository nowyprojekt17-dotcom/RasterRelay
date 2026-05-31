# Przygotowanie środowiska

RasterRelay Launcher używa Tauri, React i Vite.

Prosto mówiąc:

- Tauri robi okno aplikacji desktopowej.
- React pomaga budować ekran z małych elementów.
- Vite pomaga szybko uruchamiać i budować ekran.
- Oficjalny plugin dialog Tauri otwiera okno wyboru folderu ComfyUI.

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
