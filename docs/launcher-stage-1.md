# Launcher - etap 1 i 2

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

## Czego Launcher jeszcze nie robi

- nie instaluje ComfyUI,
- nie kopiuje plików modeli,
- nie kopiuje LoRA,
- nie uruchamia workflow,
- nie łączy się jeszcze z Photoshopem.

Przyciski Add i Install są w pierwszym etapie tylko szkicem. Pokazują użytkownikowi, gdzie taka funkcja będzie, ale nie zmieniają plików na dysku.
