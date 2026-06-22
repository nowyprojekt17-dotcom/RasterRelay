# comfy-workflows

Wersjonowane workflow ComfyUI (API format) budowane metodą workflow-first.
Iterujemy tu jakość, zanim cokolwiek owiniemy launcherem/wtyczką.

## v1-inpaint-cropstitch.json

Pierwszy działający graf. **Rdzeń Flux.2 Klein owinięty w Inpaint-Crop&Stitch, bez węzłów koloru.**

Przepływ:
`LoadImage + LoadImageMask → InpaintCropImproved (crop wokół maski + kontekst 1.5×, target 1024², blend 32px)
→ [Flux.2 Klein: UnetLoaderGGUF→ModelSamplingFlux, CLIPLoader(flux2), VAEEncode, ReferenceLatent×2 (edit), SetLatentNoiseMask, CFGGuider cfg=1, Flux2Scheduler 20 kroków/euler, SamplerCustomAdvanced, VAEDecode]
→ InpaintStitchImproved (wklejenie z wtapianiem) → SaveImage`

Idea: edytuj tylko wycinek wokół maski w dobrej rozdzielczości, wklej z powrotem z miękkim
przejściem. Korekcję koloru/tonu świadomie pominięto — najpierw sprawdzamy, ile daje sam crop+stitch.

Test: `test-images/P1075287.jpg` (puszka Monster na biurku), maska na puszce, polecenie podmiany
na granatową puszkę. Wynik: `results/v1-can_00001_.png`.

Pomiar v1 (seed 42): poza maską |ΔRGB|=0.13/255 (stitch idealny); gradient luminancji na konturze
res=6.27 < orig=10.40 (×1e-3) — brak mierzalnej linii szwu. Czas ~48s, 1024², 20 kroków.

Ocena v1: szew niewidoczny, ale OŚWIETLENIE generowanej puszki nie pasowało do sceny (zimne,
od monitora; główny refleks po złej stronie; brak ciepłego bounce od biurka). Halucynacja tekstu
„RUPNEY". To zreframe'owało problem: szew rozwiązany przez crop&stitch, dźwignia jakości = światło.

## v2-inpaint-cropstitch.json

Iteracja po ocenie v1. Zmiany względem v1:
- `context_from_mask_extend_factor` 1.5 → **2.5** (model „widzi" więcej sceny → lepiej dopasowuje światło)
- prompt: dodane jawne instrukcje światła (ciepły klucz z górnego-lewego, bounce od biurka, turkus od
  klawiatury, cień kontaktowy) + „unbranded, no text/logo"; negatyw rozszerzony o text/logo/cold flat lighting.

Wynik: `results/v2-can_00001_.png`. Światło puszki zgodne ze sceną (ciepła góra/lewa, turkus z prawej,
ciepły dół), brak halucynowanego tekstu. Szew nadal niewidoczny (poza maską |ΔRGB|=0.20; kontur res=6.26).
Pozostałe do dopracowania: odcień bardziej granat niż teal, geometria wieczka/elipsy.

## v3-lora-brushmask.json

Dwie zmiany na życzenie usera (oba węzły już były dostępne — nic nie dociągano):

1. **Multi-LoRA** — wstawiony `Power Lora Loader (rgthree)` na ścieżce model+clip
   (`UnetLoaderGGUF`+`CLIPLoader` → Power Lora Loader → `ModelSamplingFlux`/`CLIPTextEncode`).
   Jeden węzeł, wiele LoRA, każda z włącznikiem on/off i siłą. W pliku wpięte 2 realne LoRA Flux2 Klein
   (`KLEIN-Unchained-V2`, `Dever-Devil-May-Cry`) jako przykład — podmień/strój wg potrzeb. Format API:
   wpisy `LORA_n = {on, lora, strength[, strengthTwo]}`.
2. **Maska pędzlem** — źródło maski przełączone na wyjście **MASK węzła `Load Image`** (usunięto osobny
   `LoadImageMask`). To jest natywny **MaskEditor** ComfyUI: PPM na „Load Image" → „Open in MaskEditor"
   → malujesz obszar do edycji. Alternatywa w grafie: `MaskPainter` (Impact Pack, też zainstalowany).

Weryfikacja headless (`results/v3-verify_00001_.png`, oba LoRA on, maska podana jako kanał alfa RGBA =
odpowiednik namalowanej): graf przyjęty bez błędów (`node_errors: {}`), LoRA załadowane (~92s vs ~48s bez),
wynik czysty, szew niewidoczny. UWAGA: plik jest w formacie API (do uruchamiania). Do interaktywnego
malowania/UI LoRA otwórz w ComfyUI; gdyby Twoja wersja nie wczytała API-JSON jako grafu, zgłoś —
zbuduję wersję w formacie UI (most ComfyUI MCP rozłączył się w tej sesji).

