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

