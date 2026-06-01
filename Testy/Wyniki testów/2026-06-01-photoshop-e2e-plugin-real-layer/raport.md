# RasterRelay - realny test w Photoshop Beta 27.8

Data: 2026-06-01

## Co sprawdzilem

Sprawdzilem, czy wtyczka RasterRelay realnie uruchamia przeplyw:

Photoshop -> wtyczka UXP -> ComfyUI -> pobrany wynik -> nowa warstwa w Photoshopie

## Wynik

Test przeszedl. W aktywnym dokumencie Photoshop pojawila sie nowa warstwa wynikowa.

Dokument: can-source.png

Liczba warstw po koncowym tescie: 2

Warstwy:

- 1. RasterRelay - wynik E2E
- 2. Tlo

## Pliki dowodowe

- photoshop-document-with-rasterrelay-layers.psd - zapisany dokument z warstwami.
- photoshop-composite-preview.png - podglad zlozonego obrazu.
- photoshop-document-after-placement-fix-one-layer.psd - koncowy dokument po poprawce wstawiania warstwy.
- photoshop-preview-after-placement-fix-one-layer.png - koncowy podglad po poprawce.
- rasterrelay-e2e-2026-06-01T11-58-26-332Z-source.png - obraz wyslany przez wtyczke.
- rasterrelay-e2e-2026-06-01T11-58-26-332Z-mask.png - maska wyslana przez wtyczke.
- rasterrelay-e2e-2026-06-01T11-58-26-332Z-result.png - wynik pobrany przez wtyczke z ComfyUI.
- inpainting_00007_.png - wynik zapisany przez ComfyUI.
- inpainting_00008_.png - wynik zapisany przez ComfyUI po poprawce wstawiania warstwy.

## Uwaga

Pierwszy przebieg uruchomil sie dwa razy, dlatego przez chwile byly dwie warstwy `RasterRelay - wynik E2E`. Kod zostal zabezpieczony, zeby autostart E2E nie dublowal sie w jednej sesji.

W pierwszym zapisie warstwa byla zle ustawiona, bo Photoshop wstawial wynik przy aktywnym zaznaczeniu. Kod zostal poprawiony: wtyczka zapamietuje miekka maske, czysci zaznaczenie, wstawia pelny wynik i dopiero potem naklada maske na warstwe.
