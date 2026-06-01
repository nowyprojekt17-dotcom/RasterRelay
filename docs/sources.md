# Źródła i decyzje techniczne

Na start wybraliśmy Tauri + React + Vite.

## Dlaczego Tauri

Tauri pozwala zrobić małą aplikację okienkową. Jest lżejsze niż Electron, bo nie pakuje całej dużej przeglądarki do aplikacji.

## Dlaczego React

React ułatwia budowanie ekranu z małych części, na przykład kafelków statusu. Przyda się, gdy Launcher urośnie.

## Dlaczego Vite

Vite jest prostym narzędziem do uruchamiania i budowania interfejsu. Dobrze pasuje do Reacta.

## Sprawdzone dokumentacje

- Tauri 2: konfiguracja aplikacji, komendy Rust wywoływane z UI.
- React: renderowanie list i prosty stan komponentu.
- Vite: minimalne skrypty `dev`, `build`, `preview` oraz konfiguracja React TypeScript.
- Adobe Photoshop UXP: manifest v5, panele, host `PS`, uprawnienia sieciowe.
- Photoshop API: dostęp do aktywnego dokumentu, odczyt `selection.bounds` i zasada używania `executeAsModal` przy przyszłych zmianach w obrazie.
- UXP storage: prywatny folder danych wtyczki przez `localFileSystem.getDataFolder()`.
- Photoshop `document.saveAs.png(...)`: eksport aktywnego dokumentu jako PNG-kopia do paczki inpaintingu.
- Photoshop Imaging API `imaging.getSelection(...)`: odczyt pikselowej reprezentacji aktywnego zaznaczenia do maski inpaintingu.
- Photoshop Imaging API `imaging.putLayerMask(...)`: próba wpisania pikseli aktywnej selekcji jako maski nowej warstwy wynikowej.
- ComfyUI server routes: `/upload/image` służy do wysłania obrazów wejściowych, a `/prompt` do dodania workflow do kolejki.
- ComfyUI server routes: `/history/{prompt_id}` służy do odczytu metadanych wyniku, a `/view` do pobrania obrazu.
- Photoshop `batchPlay` / `placeEvent`: próba wstawienia pobranego PNG do aktywnego dokumentu jako nowej warstwy.

Nie dodaliśmy Tailwinda, bibliotek UI ani bibliotek ikon. Pierwszy ekran i pierwszy panel mają być możliwie proste.

## Dlaczego dodaliśmy plugin dialog

W etapie 2 dodaliśmy oficjalny `@tauri-apps/plugin-dialog` oraz `tauri-plugin-dialog`.

Ta paczka jest potrzebna do jednego zadania: otwarcia systemowego okna wyboru folderu. Dzięki temu użytkownik nie musi ręcznie wpisywać ścieżki do ComfyUI.

Nie jest to biblioteka UI i nie zmienia wyglądu aplikacji. To małe narzędzie do bezpiecznego wyboru folderu.

## Decyzja z etapu 3

LoRA zapisujemy w `ComfyUI/models/loras`.

Pliki GGUF dla lokalnego modelu FLUX.2 zapisujemy w `ComfyUI/models/unet`, bo lokalny node `UnetLoaderGGUF` widzi `flux-2-klein-9b-Q4_K_M.gguf` właśnie w tym folderze.

Oficjalna dokumentacja ComfyUI dla Flux.2 Klein mówi, że 9B używa text encodera `qwen_3_8b_fp8mixed.safetensors` i VAE `flux2-vae.safetensors`. Lokalna instalacja ma oba te pliki.

Źródła:

- https://docs.comfy.org/tutorials/flux/flux-2-klein
- https://comfy.org/ko/workflows/image_flux2_klein_image_edit_9b_base-563f9b5f6ce3/

## Decyzja o Photoshop UXP

Pierwszy panel Photoshopa budujemy jako prostą wtyczkę UXP bez dodatkowego frameworka.

Powód jest prosty: na tym etapie potrzebujemy sprawdzić, czy Photoshop widzi naszą wtyczkę i czy panel potrafi rozmawiać z lokalnym ComfyUI. Zwykły HTML, CSS i JavaScript wystarczą, więc nie dokładamy kolejnej biblioteki.

Wersja docelowa hosta: **Photoshop Beta 27.8**. Manifest wtyczki ustawiamy na `minVersion: "27.8.0"`, żeby nie obiecywać działania na starszych Photoshopach.
