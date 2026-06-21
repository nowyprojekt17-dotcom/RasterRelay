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
