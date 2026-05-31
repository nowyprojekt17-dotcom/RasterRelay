# Launcher - etap 1, 2 i 3

Launcher jest małą aplikacją pomocniczą dla RasterRelay.

Jego pierwsze zadanie jest proste: sprawdzić, czy lokalne ComfyUI wygląda na gotowe do pracy.

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
- ile jest plików `.gguf`.

## Co dodaje etap 2

Etap 2 dodaje ręczne wskazanie folderu ComfyUI.

Jeżeli autoskan nie znajdzie ComfyUI, użytkownik może kliknąć `Wybierz folder ComfyUI` i wskazać folder samodzielnie. Launcher sprawdzi, czy w folderze jest plik `main.py`.

Jeżeli go nie ma, Launcher pokaże prosty komunikat, że to nie jest główny folder ComfyUI.

## Co dodaje etap 3

Etap 3 dodaje bezpieczne dodawanie dwóch typów plików:

- LoRA do `models/loras`,
- GGUF do `models/diffusion_models`.

Launcher nie kopiuje pliku od razu po wyborze. Najpierw sprawdza rozszerzenie, folder docelowy i duplikaty, a potem pokazuje panel potwierdzenia.

Jeśli folder docelowy nie istnieje, Launcher tworzy go dopiero po kliknięciu `Kopiuj`.

Jeśli plik o tej samej nazwie już istnieje, Launcher odmawia kopiowania i niczego nie nadpisuje.

## Czego Launcher jeszcze nie robi

- nie instaluje ComfyUI,
- nie kopiuje plików modeli,
- nie kopiuje LoRA,
- nie uruchamia workflow,
- nie łączy się jeszcze z Photoshopem.

Przyciski Add dla LoRA i GGUF działają od etapu 3. Pozostałe przyciski Add i Install nadal są szkicem.
