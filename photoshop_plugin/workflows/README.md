# Workflow API dla panelu Photoshop

Ten folder jest miejscem na workflow API JSON eksportowany z ComfyUI.

Panel szuka dwóch plików:

- `inpainting-api.json` - prawdziwy workflow API z ComfyUI,
- `inpainting-api.mapping.json` - informacja, do których node'ów wstawić obraz, maskę, prompt i LoRA.

W repo są teraz dwa typy plików:

- `inpainting-api.example.json`,
- `inpainting-api.mapping.example.json`.
- `inpainting-api.json`,
- `inpainting-api.mapping.json`.

Pliki `.example.json` są tylko przykładem. Pliki bez `.example` są pierwszym prawdziwym workflow API dla lokalnego FLUX.2 Klein GGUF.

Ten workflow został sprawdzony przez lokalne ComfyUI `/prompt` na małym obrazie kontrolnym. Kolejny test musi odbyć się już w Photoshop Beta 27.8 na realnym dokumencie.

Launcher ma dwa przyciski w sekcji `Workflow API`: `Dodaj workflow API` i `Dodaj mapping`. One zapisują prawdziwe pliki pod stałymi nazwami oczekiwanymi przez panel Photoshopa. Mapping musi mieć wejścia `sourceImage`, `selectionMask` i `prompt`.

LoRA są mapowane osobno. Dla jednego prostego workflow można nadal użyć pól `loraName` i `loraStrength`. Dla kilku LoRA używamy listy `inputs.loras`, gdzie każdy slot wskazuje node LoRA i jego pola `lora_name`, `strength_model` oraz `strength_clip`.

Aktualny mapping używa też `loraChain`. To znaczy: workflow bazowy działa bez LoRA, a panel Photoshopa dodaje node'y `LoraLoader` dynamicznie dopiero wtedy, gdy użytkownik wpisze nazwy LoRA.

## Jak będzie działać kolejny krok

1. W ComfyUI budujemy workflow inpaintingu dla FLUX/GGUF/LoRA.
2. Eksportujemy go jako API JSON.
3. Zapisujemy go tutaj jako `inpainting-api.json`.
4. Ustawiamy właściwe node ID w `inpainting-api.mapping.json`.
5. Panel Photoshopa podstawia nazwy uploadowanych plików i wysyła workflow do `/prompt`.
