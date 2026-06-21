# RasterRelay — Rebuild Plan

**Decyzja (2026-06-21):** budujemy **launcher od zera + nową, lepiej przemyślaną wtyczkę**.
Obecny kod (`launcher/`, `photoshop_plugin/`) staje się **materiałem referencyjnym**, nie
fundamentem. Stary pipeline inpaintingu usunięty w resecie `d88835d`; cała historia
sprzed niego jest w gicie, gdyby trzeba coś podejrzeć/odzyskać.

## Co zostaje niezależnie od przebudowy

- `assets/brand/` — logo.
- `test-images/` — obrazy referencyjne do testów.
- Wiedza w sekcji „Lekcje" niżej (drogo okupiona pomiarami).
- Środowisko ComfyUI (port, modele, izolowany runtime) — opis niżej.

## Obecny kod jako referencja — co warto przejąć, co odpuścić

**Działało dobrze (warto powtórzyć w nowym):**
- Panel mapping-driven: `panel.js` ustawiał `mapping.inputs.<klucz> → [nodeId, slot]`.
  Rozdział „workflow jako dane" od „logiki panelu" był słuszny — graf można było zmieniać
  bez ruszania kodu. To zatrzymujemy jako wzorzec.
- Launcher jako orkiestrator procesów: jeden przycisk startował ComfyUI + Photoshop +
  UXP + ładowanie panelu. To realny pain killer dla usera nietechnicznego.
- Izolowany runtime ComfyUI w `%TEMP%` (osobny input/output/db) — nie brudził głównej instalacji.

**Bolało / do przemyślenia (czego nie powtarzać):**
- Rozmiar: `lib.rs` ~2940 l., `App.tsx` ~1471 l., `panel.js` ~3398 l. — monolity z dużą
  ilością boilerplate'u (struktury readiness, walidacje instalacji, 3 osobne pollery statusu).
- Kontrakt węzłów zaszyty na sztywno w launcherze (lista klas `RasterRelay*`) — sprzęgał
  launcher z konkretnym grafem. Nowy launcher nie powinien znać nazw węzłów.
- Cała konfiguracja (jakość, LoRA) w launcherze, a panel tylko ją czytał — rozważyć
  przeniesienie większości decyzji do samej wtyczki (mniej skakania między oknami).

## Nowy launcher — propozycja lean MVP (do uzgodnienia)

Najmniejsza pętla, która daje wartość; reszta dopiero gdy potrzebna:
1. Wykryj / wskaż folder ComfyUI, sprawdź obecność wymaganych modeli.
2. Jeden przycisk: start ComfyUI + Photoshop + UXP + załaduj panel.
3. Status: czy ComfyUI odpowiada, czy panel załadowany.

Odłożone do czasu realnej potrzeby (YAGNI): instal-slot na workflow/mapping, walidacja
kontraktu węzłów, centrum jakości, UI LoRA. Część z tego może w ogóle wejść do wtyczki.

Stack: do decyzji — Tauri+React (sprawdzone na Windows, mocna kontrola procesów w Rust)
vs coś lżejszego. Rekomendacja: zostać przy Tauri, ale napisać szczupło.

## Nowa wtyczka — propozycja lean MVP (do uzgodnienia)

Rdzeń pętli: zaznacz obszar → wpisz prompt → generuj przez ComfyUI → wstaw wynik.
Wzorzec mapping-driven zostaje (workflow = dane). **Otwarte:** co konkretnie ma być
„bardziej przemyślane" — to wie tylko user (patrz pytania niżej).

## Środowisko ComfyUI (bez zmian)

ComfyUI `127.0.0.1:8188`. Izolowany runtime w `%TEMP%\RasterRelay\comfy-runtime`.
Modele: `flux-2-klein-9b-Q4_K_M.gguf` (unet), `qwen_3_8b_fp8mixed.safetensors` (text enc),
`flux2-vae.safetensors` (vae). RTX 3090 24GB. Custom nody instalowane jako KOPIA →
po edycji reinstal + restart ComfyUI.

## Lekcje z usuniętego pipeline'u (projektując nowy graf)

- Klein GGUF ignoruje concat conditioning → InpaintModelConditioning bezużyteczny;
  działa DifferentialDiffusion (soft maska = gradient denoise per piksel).
- Korekta koloru tylko przy szwie (seam-band) — wnętrze obiektu ma prawo różnić się od tła.
- Upscale małych wycinków NIE poprawia ostrości na Flux2 Klein (zmierzone). Generuj natywnie ≤~1.15MP.
- Rozkład zmian tonu bimodalny (dryf <0.05 vs intencja >0.15) — próg ~0.10 separuje.
- Globalny Reinhard nieskuteczny; dyfuzja tonu LF otoczenia do wnętrza działała.
- ICC: PNG z ComfyUI bez tagu → dokument roboczy PS trzymaj w sRGB.
- Pomiar jakości: dL_seam + seam_step vs naturalna zmienność oryginału (nie wartość absolutna).

## Otwarte decyzje (zanim ruszy kod)

1. **Wtyczka — co „lepiej przemyślane"?** Co frustrowało w starym panelu (UX? wolność/precyzja
   zaznaczenia? prompt? podgląd wariantów? szybkość?). To wyznacza priorytety v1.
2. **Launcher — stack:** zostać przy Tauri+React czy spróbować lżej?
3. **Podział odpowiedzialności launcher ↔ wtyczka:** ile konfiguracji przenieść do panelu?
4. **Kolejność:** zaczynamy od launchera (środowisko wstaje) czy od wtyczki (pętla edycji),
   na tym samym starym grafie jako tymczasowym, czy od razu projektujemy nowy graf?
