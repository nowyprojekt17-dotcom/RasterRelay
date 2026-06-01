# Launcher - etapy 1-4

Launcher jest małą aplikacją pomocniczą dla RasterRelay.

Jego pierwsze zadanie jest proste: sprawdzić, czy lokalne ComfyUI wygląda na gotowe do pracy, a potem pomóc je uruchomić bez ręcznego wpisywania komend.

## Co Launcher sprawdza

- czy znaleziono folder ComfyUI,
- czy folder ma plik `main.py`,
- czy istnieje środowisko Python lub portable Python,
- czy istnieje folder `custom_nodes`,
- czy istnieje folder `models`,
- czy istnieje folder `models/loras`,
- czy istnieje folder `models/diffusion_models`,
- czy istnieje folder `models/text_encoders`,
- czy jest miejsce na przyszłe `rasterrelay_nodes`,
- ile jest custom nodes,
- ile jest plików LoRA,
- ile jest plików `.gguf`,
- czy workflow API dla panelu Photoshopa jest gotowy.

## Co dodaje etap 2

Etap 2 dodaje ręczne wskazanie folderu ComfyUI.

Jeżeli autoskan nie znajdzie ComfyUI, użytkownik może kliknąć `Wybierz folder ComfyUI` i wskazać folder samodzielnie. Launcher sprawdzi, czy w folderze jest plik `main.py`.

Jeżeli go nie ma, Launcher pokaże prosty komunikat, że to nie jest główny folder ComfyUI.

## Co dodaje etap 3

Etap 3 dodaje bezpieczne dodawanie dwóch typów plików:

- LoRA do `models/loras`,
- GGUF do `models/unet`.

Launcher nie kopiuje pliku od razu po wyborze. Najpierw sprawdza rozszerzenie, folder docelowy i duplikaty, a potem pokazuje panel potwierdzenia.

Jeśli folder docelowy nie istnieje, Launcher tworzy go dopiero po kliknięciu `Kopiuj`.

Jeśli plik o tej samej nazwie już istnieje, Launcher odmawia kopiowania i niczego nie nadpisuje.

## Co dodaje etap 4

Etap 4 dodaje podstawową aktywację ComfyUI z Launchera.

Launcher potrafi:

- sprawdzić, czy ComfyUI odpowiada pod `http://127.0.0.1:8188`,
- uruchomić `main.py` z wybranego folderu ComfyUI,
- użyć Pythona z `venv`, portable Python obok folderu `ComfyUI` albo systemowego `python`,
- pokazać, czy ComfyUI jest aktywne,
- zatrzymać tylko proces, który sam uruchomił,
- pokazać, czy workflow API dla panelu Photoshopa jest gotowy.
- pokazać, czy Photoshop Beta jest zainstalowany,
- uruchomić Photoshop Beta z przycisku `Start Photoshop`.

To ważne zabezpieczenie: jeśli użytkownik odpalił ComfyUI samodzielnie poza Launcherem, Launcher nie zamyka tego procesu na siłę.

## Photoshop Beta

Launcher sprawdza standardową ścieżkę:

```text
C:\Program Files\Adobe\Adobe Photoshop (Beta)\Photoshop.exe
```

Jeśli plik istnieje, przycisk `Start Photoshop` uruchamia Photoshop Beta. Launcher nie instaluje panelu automatycznie w Photoshopie; manifest nadal trzeba dodać przez Adobe UXP Developer Tool.

## Workflow API

Launcher sprawdza:

- `photoshop_plugin/workflows/inpainting-api.json`,
- `photoshop_plugin/workflows/inpainting-api.mapping.json`.

Jeśli tych plików nie ma albo mapping nie ma `status: "ready"`, Launcher pokazuje, że workflow wymaga pracy. To jest oczekiwane, dopóki nie wyeksportujemy prawdziwego workflow z ComfyUI.

Jeśli ComfyUI działa, Launcher próbuje też odczytać `http://127.0.0.1:8188/object_info`. Dzięki temu może pokazać, czy lokalna instalacja ma podstawowe node'y potrzebne do inpaintingu, na przykład `LoadImage`, `SaveImage`, `KSampler`, `CLIPTextEncode`, `VAEDecode` i `LoraLoader`.

## Czego Launcher jeszcze nie robi

- nie instaluje ComfyUI,
- nie instaluje brakujących bibliotek Pythona,
- nie buduje sam workflow FLUX/GGUF/LoRA,
- nie instaluje automatycznie panelu w Photoshopie.

Przyciski Add dla LoRA i GGUF działają od etapu 3. Panel ComfyUI działa od etapu 4. Workflow API jest sprawdzany.

Uwaga praktyczna z lokalnego komputera: model `flux-2-klein-9b-Q4_K_M.gguf` jest widoczny w `models/unet`, a node `UnetLoaderGGUF` używa właśnie tego folderu. Dlatego Launcher instaluje GGUF do `models/unet`.
