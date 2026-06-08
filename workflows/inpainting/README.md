# Workflow inpaintingu

To miejsce jest przygotowane pod pierwszy workflow RasterRelay.

Docelowo workflow ma obsługiwać:

- model bazowy GGUF,
- działanie bez LoRA,
- działanie z jedną LoRA,
- działanie z kilkoma LoRA, jeśli użyte node'y ComfyUI na to pozwolą,
- prompt użytkownika,
- obraz z aktywnego dokumentu Photoshopa,
- maskę z zaznaczenia Photoshopa,
- wynik zwracany jako nowa warstwa z maską.

## Kontrakt zadania

Plik `job-contract.v1.json` opisuje pierwszy prosty format paczki zadania.

Prosto mówiąc: to lista informacji, które Photoshop musi przekazać dalej, żeby ComfyUI wiedziało, co zrobić.

Na teraz paczka zawiera:

- źródło zadania, czyli panel Photoshop UXP,
- aktywny dokument,
- granice zaznaczenia,
- plik PNG z aktywnego dokumentu,
- maskę PNG generacji dla ComfyUI oraz osobną maskę widoczności warstwy Photoshopa,
- prompt,
- informację, że bazowy model jest GGUF,
- miejsce na jedną albo kilka LoRA i ich siłę,
- nazwy plików po uploadzie do ComfyUI,
- oczekiwany wynik jako nowa warstwa z maską.
- ścieżkę do pobranego wyniku z ComfyUI,
- informację, czy wynik został wstawiony do Photoshopa jako warstwa.
- informację, czy maska warstwy została utworzona z aktywnej selekcji.

Panel Photoshopa wysyła obraz i maskę do lokalnego ComfyUI przez `/upload/image`. Ma też kod do wysłania workflow do `/prompt`, ale wymaga prawdziwego workflow API JSON.

Pierwszy prawdziwy workflow API znajduje się teraz w:

- `photoshop_plugin/workflows/inpainting-api.json`,
- `photoshop_plugin/workflows/inpainting-api.mapping.json`.

Został przygotowany pod lokalne ComfyUI z:

- `UnetLoaderGGUF`,
- `flux-2-klein-9b-Q4_K_M.gguf`,
- `qwen_3_8b_fp8mixed.safetensors`,
- `flux2-vae.safetensors`.

Workflow przeszedł lokalny test `/prompt` na małym obrazie kontrolnym i zapisał wynik w `E:\AI\ComfyUI\output\RasterRelay`.

Ten test można powtórzyć komendą:

```powershell
cd C:\Users\Mierz\Desktop\RasterRelay
.\scripts\verify-comfy-workflow.ps1
```

To nie testuje Photoshopa. To sprawdza, czy lokalne ComfyUI, modele, node'y i API workflow są gotowe.

W panelu Photoshopa jest podobny, lżejszy przycisk `Sprawdź gotowość`. On nie wysyła obrazu do generowania, tylko sprawdza aktywny dokument, zaznaczenie, ComfyUI i wymagane node'y workflow.

## Maska zaznaczenia

Panel próbuje tworzyć maskę przez `imaging.getSelection`, czyli przez pikselową reprezentację aktywnego zaznaczenia. To jest lepsze od prostokąta, bo zachowuje nieregularny kształt i miękkie krawędzie.

RasterRelay używa teraz dwóch ról maski. `selectionMask` w mappingu workflow jest maską generacji wysyłaną do `LoadImageMask -> SetLatentNoiseMask`; plugin automatycznie dodaje jej miękki halo zależny od jakości, żeby FLUX.2 Klein miał kontekst przejścia. Maska warstwy Photoshopa jest przechowywana osobno jako `layerMaskData` i kontroluje finalną widoczność wyniku.

Jeśli Photoshop nie pozwoli odczytać selekcji przez Imaging API, panel ma przerwać zadanie i pokazać jasny błąd. Nie używamy już prostokątnej maski awaryjnej, bo może dać twardą krawędź i fałszywy wynik testu.

## Kolejka ComfyUI

ComfyUI przyjmuje workflow przez endpoint `/prompt`.

Panel szuka workflow w:

- `photoshop_plugin/workflows/inpainting-api.json`,
- `photoshop_plugin/workflows/inpainting-api.mapping.json`.

Na razie są tylko przykłady `.example.json`. Prawdziwy workflow musi zostać zbudowany i wyeksportowany z ComfyUI.

Ważne: workflow musi mieć miejsca na:

- `sourceImage` z uploadu,
- `selectionMask` z uploadu,
- prompt,
- prosty preset jakości,
- model bazowy GGUF,
- zero, jedną albo kilka LoRA.

Panel Photoshopa umie przekazać wiele LoRA jako listę. W mappingu najczytelniejszy układ to:

- `inputs.loras[0]` dla pierwszego node'a LoRA,
- `inputs.loras[1]` dla drugiego node'a LoRA,
- dalej tak samo, jeśli workflow ma więcej slotów.

Każdy slot może mieć `name`, `strengthModel` i `strengthClip`. Jeśli użytkownik nie wpisze LoRA, panel przekaże pustą nazwę i siłę `0` tylko do slotów opisanych w mappingu. Prawdziwy workflow musi być zbudowany tak, żeby taki pusty slot nie psuł generowania.

Panel przekazuje też `steps` i `cfg` z prostego wyboru jakości. Dzięki temu użytkownik nietechniczny wybiera tylko `Szybki test`, `Dobra jakość` albo `Dokładna edycja`, a workflow dostaje konkretne liczby.

## Odbiór wyniku

Po zaakceptowaniu workflow przez ComfyUI panel używa:

- `/history/{prompt_id}` do sprawdzania, czy wynik już istnieje,
- `/view` do pobrania obrazu wynikowego.

Panel zapisuje pobrany PNG w prywatnym folderze danych wtyczki i próbuje wstawić go do aktywnego dokumentu Photoshopa jako nową warstwę.

Po wstawieniu warstwy panel próbuje utworzyć maskę warstwy z aktywnego zaznaczenia przez Photoshop Imaging API. To ma utrzymać edycję w zaznaczonym obszarze i daje lepszą kontrolę niż sama płaska grafika bez maski.

Jeśli automatyczne wstawienie warstwy się nie uda, paczka zadania zapisze błąd w `outputs.resultImage.photoshop.error`.

Jeśli wstawienie warstwy się uda, ale maska nie zostanie utworzona, paczka zadania zapisze szczegóły w `outputs.resultImage.photoshop.layerMask`.

## Źródła workflow

Pobraliśmy oficjalny workflow referencyjny ComfyUI dla `Flux.2 [Klein] 9B: Image Edit` i zapisaliśmy go jako:

- `official-flux2-klein-9b-image-edit.workflow.json`.

Ten plik jest workflow UI z ComfyUI, a nie bezpośrednim API promptem. Nasz `inpainting-api.json` jest prostszą wersją API, zbudowaną pod panel Photoshopa i sprawdzoną na lokalnym ComfyUI.
