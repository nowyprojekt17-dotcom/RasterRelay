# Arsenał węzłów ComfyUI — pod workflow RasterRelay

Zainstalowano 11 pakietów custom node (sklonowane do `E:\AI\ComfyUI\custom_nodes`,
zależności Pythona zainstalowane w `.venv`). Dobór celuje w nasze wyzwania: edycja
tylko wycinka + **bezszwowe wklejenie**, dopasowanie koloru/tonu/ziarna na szwie,
precyzyjne maski i most do przyszłej wtyczki.

> Status weryfikacji importu: **oczekuje** — ComfyUI nie startuje z powodu niezależnego
> problemu z torch (wersja CPU, patrz `KONTEKST-DECYZJE.md`). Pakiety są zainstalowane;
> czysty import potwierdzę po naprawie torch.

| # | Pakiet | Co robi | Jak się przyda u nas |
|---|--------|---------|----------------------|
| 1 | **ComfyUI-Inpaint-CropAndStitch** (lquesada) | Przycina obraz do okolicy maski, generuje inpainting w optymalnej rozdzielczości, wkleja wynik z powrotem z wtapianiem brzegów. | **Rdzeń projektu** — „edytuj mały wycinek dużego zdjęcia" + bezszwowe wklejenie. Najważniejszy z listy. |
| 2 | **comfyui-inpaint-nodes** (Acly) | VAE Encode (Inpaint), wypełnianie i blur maski, Fooocus inpaint patch. | Lepsze przygotowanie zamaskowanego obszaru przed samplerem; kontrola jak maska wchodzi do generacji. |
| 3 | **ComfyUI-Image-Filters** (spacepxl) | Guided filter, alpha matte, blur, color match, remap range, dilate/erode na float. | Precyzyjne wygładzanie krawędzi maski (guided filter) i miękkie przejścia/kolor na szwie. |
| 4 | **was-node-suite-comfyui** (WAS) | 200+ narzędzi: tryby mieszania obrazów, histogram, Color Match, operacje na maskach, korekcja. | Arsenał do dopasowania tonu/koloru wycinka do otoczenia i kompozycji wyniku. |
| 5 | **ComfyUI_LayerStyle** (chflame163) | Kompozycja jak warstwy PS: tryby blend, ImageBlendAdvance, maski, korekcja koloru, RestoreCropBox. | Profesjonalny paste-back z trybami mieszania i dopasowaniem — naturalny język „warstw". |
| 6 | **ComfyUI-post-processing-nodes** (EllangoK) | Film grain, blend, color correct, dithering, sharpen, vignette. | Dopasowanie ziarna/szumu wycinka do reszty — świeża generacja jest „za czysta", co zdradza łatę. |
| 7 | **ComfyUI-segment-anything-2** (kijai) | SAM2 — segmentacja obiektu do precyzyjnej maski (klik/prompt → maska). | Szybkie, dokładne maski do testów; ewentualnie auto-maska w przyszłej wtyczce. |
| 8 | **ComfyUI-Florence2** (kijai) | Florence-2: detekcja, captioning, grounding — „znajdź obiekt z opisu" → bbox/maska. | Auto-wykrywanie regionu z tekstu i wsparcie promptu; automatyzacja maski. |
| 9 | **ComfyUI-Easy-Use** (yolain) | Pipe'y, presety samplerów, węzły inpaint/loader, porządkowanie grafu. | Szybsze, czytelniejsze składanie i iterowanie naszego workflow. |
| 10 | **comfyui-tooling-nodes** (Acly) | I/O dla zewnętrznych aplikacji: obraz/maska z base64, zwrot obrazu przez API. | **Most do wtyczki Photoshop** — panel przekaże wycinek i maskę, odbierze wynik bez plików pośrednich. |
| 11 | **ComfyUI-Detail-Daemon** (Jonseed) | Zwiększa detal podczas samplingu (modulacja sigm), bez zmiany kompozycji. | Ostrzejszy detal w generowanym wycinku — przeciwdziała „rozmytej łacie". |

## Już zainstalowane wcześniej (przydatne, nie dublowane)

`ComfyUI-KJNodes`, `ComfyUI_essentials`, `ComfyUI-Impact-Pack`, `ComfyUI-Inspire-Pack`,
`masquerade-nodes-comfyui` (operacje na maskach), `comfyui_segment_anything` (SAM1),
`comfyui-lama-remover` (usuwanie obiektów LaMa), `ComfyUI_IPAdapter_plus` (referencja stylu),
`ComfyUI_UltimateSDUpscale`, `comfyui_controlnet_aux`, `rgthree-comfy`, `ComfyUI-GGUF` (loader modelu).
