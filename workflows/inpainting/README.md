# Workflow inpaintingu

To miejsce jest przygotowane pod pierwszy workflow RasterRelay.

Docelowo workflow ma obsługiwać:

- model bazowy GGUF,
- działanie bez LoRA,
- działanie z jedną LoRA,
- działanie z kilkoma LoRA, jeśli użyte node'y ComfyUI na to pozwolą,
- prompt użytkownika,
- maskę z zaznaczenia Photoshopa,
- wynik zwracany jako nowa warstwa.

Na tym etapie nie dodajemy jeszcze gotowego workflow. Najpierw budujemy Launcher i sprawdzanie gotowości środowiska.
