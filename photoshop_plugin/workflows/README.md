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

Pliki `.example.json` są tylko przykładem. Pliki bez `.example` są prawdziwym workflow API dla FLUX.2 Klein GGUF.

## Architektura: ReferenceLatent (nie inpainting)

FLUX.2 Klein 9B to model **image editing**, nie inpainting. Wykorzystuje **ReferenceLatent** — obraz referencyjny trafia jako conditioning do modelu.

### Przepływ danych

```
Source Image ──→ VAEEncode ──→ LATENT
                                    ↓
Text Prompt ──→ CLIPTextEncode ──→ CONDITIONING
                                    ↓
                ReferenceLatent(CONDITIONING, LATENT) ──→ conditioned CONDITIONING
                                    ↓
                EmptyFlux2LatentImage ──→ pusty LATENT (docelowy rozmiar)
                                    ↓
                CFGGuider(model, positive, negative, cfg) ──→ GUIDER
                                    ↓
                SamplerCustomAdvanced(NOISE, GUIDER, SAMPLER, SIGMAS, LATENT) ──→ nowy LATENT
                                    ↓
                VAEDecode ──→ Generated Image
                                    ↓
                ImageCompositeMasked(original, generated, mask) ──→ Final Image
```

### Kluczowe node'y

| ID | Typ | Rola |
|----|-----|------|
| 10 | LoadImage | Obraz źródłowy (reference image) |
| 11 | LoadImageMask | Maska (channel: red, MASK output → ImageCompositeMasked) |
| 20 | UnetLoaderGGUF | Model FLUX.2 Klein 9B GGUF |
| 21 | ModelSamplingFlux | Parametry samplingu (width, height) |
| 30 | CLIPLoader | Text encoder (Qwen 3 8B) |
| 31 | CLIPTextEncode | Positive prompt |
| 32 | CLIPTextEncode | Negative prompt (pusty) |
| 40 | VAELoader | VAE (flux2-vae) |
| 41 | VAEEncode | Koduje obraz referencyjny → LATENT |
| 50 | EmptyFlux2LatentImage | Pusty latent w docelowym rozmiarze |
| 51 | ReferenceLatent | Conditioning pozytywne z referencją |
| 52 | ReferenceLatent | Conditioning negatywne z referencją |
| 60 | RandomNoise | Szum dla samplera |
| 61 | KSamplerSelect | Sampler (euler) |
| 62 | Flux2Scheduler | Harmonogram (steps, width, height) |
| 63 | CFGGuider | Guider z modelem i conditioning |
| 64 | SamplerCustomAdvanced | Główny sampler |
| 65 | VAEDecode | Dekoduje latent → obraz |
| 66 | ImageCompositeMasked | Kompozytuje wynik z oryginałem |
| 80 | SaveImage | Zapisuje wynik |

### Dlaczego nie inpainting?

Stary workflow używał `SetLatentNoiseMask` — szum był nakładany tylko na zaznaczony obszar, a model generował tylko tam. Problem: model nie "widział" całego obrazu jako kontekst.

Nowy workflow wysyła **cały obraz** jako conditioning przez `ReferenceLatent`. Model generuje **cały obraz od zera**, ale guided przez referencję. Następnie `ImageCompositeMasked` kompozytuje tylko zaznaczony obszar z wyniku z oryginałem.

To daje lepsze rezultaty, bo model ma pełny kontekst obrazu wejściowego.

## Jak będzie działać kolejny krok

1. W ComfyUI budujemy workflow z ReferenceLatent dla FLUX/GGUF/LoRA.
2. Eksportujemy go jako API JSON.
3. Zapisujemy go tutaj jako `inpainting-api.json`.
4. Ustawiamy właściwe node ID w `inpainting-api.mapping.json`.
5. Panel Photoshopa podstawia nazwy uploadowanych plików i wysyła workflow do `/prompt`.

Launcher ma dwa przyciski w sekcji `Workflow API`: `Dodaj workflow API` i `Dodaj mapping`. One zapisują prawdziwe pliki pod stałymi nazwami oczekiwanymi przez panel Photoshopa. Mapping musi mieć wejścia `sourceImage`, `selectionMask` i `prompt`.

LoRA są mapowane osobno. Dla jednego prostego workflow można nadal użyć pól `loraName` i `loraStrength`. Dla kilku LoRA używamy listy `inputs.loras`, gdzie każdy slot wskazuje node LoRA i jego pola `lora_name`, `strength_model` oraz `strength_clip`.

Aktualny mapping używa też `loraChain`. To znaczy: workflow bazowy działa bez LoRA, a panel Photoshopa dodaje node'y `LoraLoader` dynamicznie dopiero wtedy, gdy użytkownik wpisze nazwy LoRA.
