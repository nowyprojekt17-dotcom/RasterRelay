# RasterRelay Photoshop Plugin

To jest pierwszy, mały szkielet wtyczki do Photoshopa.

Docelowa wersja hosta na tym etapie: **Photoshop Beta 27.8**. Manifest wtyczki ma `minVersion: "27.8.0"`, więc nie projektujemy tego panelu pod starsze wersje Photoshopa.

Na tym etapie panel:

- pokazuje funkcję `Inpainting Brush Tool`,
- sprawdza, czy ComfyUI odpowiada pod `http://127.0.0.1:8188`,
- sprawdza, czy Photoshop ma aktywny dokument,
- sprawdza, czy dokument ma zaznaczenie,
- ma pole promptu,
- ma prosty wybór jakości: szybki test, dobra jakość albo dokładna edycja,
- ma pole na jedną albo kilka LoRA,
- pozwala ustawić wspólną siłę LoRA albo dopisać siłę przy konkretnej nazwie, na przykład `style.safetensors:0.8`,
- eksportuje aktywny dokument jako PNG,
- tworzy maskę PNG z pikseli zaznaczenia Photoshopa,
- zapisuje paczkę zadania `rasterrelay-inpainting-job.json` w prywatnym folderze danych wtyczki.
- po kliknięciu `Przygotuj edycję` wysyła obraz i maskę do lokalnego ComfyUI przez `/upload/image`,
- jeśli wtyczka ma prawdziwy workflow API JSON, wysyła go do kolejki ComfyUI przez `/prompt`,
- po `promptId` odpyta `/history/{prompt_id}`,
- pobierze pierwszy obraz wynikowy przez `/view`,
- spróbuje wstawić wynik do aktywnego dokumentu jako nową warstwę,
- spróbuje dodać do tej warstwy maskę z aktywnego zaznaczenia.
- ma przycisk `Sprawdź gotowość`, który przed generowaniem sprawdza dokument, ComfyUI i node'y workflow.

Panel nadal potrzebuje prawdziwego workflow FLUX/GGUF/LoRA, żeby zrobić realną edycję. Kod drogi powrotnej wyniku jest już przygotowany.

## Dlaczego UXP

UXP to oficjalny sposób Adobe na budowanie nowoczesnych paneli do Photoshopa.

Prosto mówiąc: `manifest.json` mówi Photoshopowi, że ten folder jest wtyczką, a `index.html` pokazuje panel.

## Jak uruchomić panel w Photoshopie

Najprostsza droga na etapie pracy:

1. Otwórz Adobe UXP Developer Tool.
2. Kliknij `Add Plugin`.
3. Wskaż plik:

```text
C:\Users\Mierz\Desktop\RasterRelay\photoshop_plugin\manifest.json
```

4. Kliknij `Load`.
5. W Photoshopie znajdź panel `RasterRelay`.

## Co sprawdzić

- Czy panel `RasterRelay` pojawia się w Photoshopie.
- Czy przycisk `Sprawdź ComfyUI` wykrywa ComfyUI po uruchomieniu go z Launchera.
- Czy przycisk `Sprawdź dokument` widzi aktywny dokument w Photoshopie.
- Czy `Zapisz paczkę zadania` wymaga promptu i zaznaczenia.
- Czy `Zapisz paczkę zadania` tworzy plik źródłowy PNG, maskę PNG i JSON zadania.
- Czy `Sprawdź gotowość` pokazuje, że dokument, ComfyUI i workflow są gotowe.
- Czy `Przygotuj edycję` zapisuje paczkę zadania, sprawdza ComfyUI i wysyła PNG obrazu oraz maski do ComfyUI.
- Czy bez prawdziwego `photoshop_plugin/workflows/inpainting-api.json` panel pokazuje jasny błąd zamiast udawać generowanie.
- Po dodaniu prawdziwego workflow: czy panel pobiera wynik z ComfyUI i wstawia go jako nową warstwę.

## Co jest w paczce zadania

Paczka zadania to mały plik JSON. Zawiera:

- nazwę i rozmiar dokumentu,
- granice zaznaczenia,
- ścieżkę do PNG aktywnego dokumentu,
- ścieżkę do maski PNG z zaznaczenia,
- nazwy plików po uploadzie do ComfyUI,
- `promptId` po wysłaniu workflow do `/prompt`, jeśli prawdziwy workflow jest podłączony,
- ścieżkę do pobranego wyniku,
- informację, czy wynik został wstawiony do Photoshopa jako warstwa,
- informację, czy maska warstwy została utworzona,
- prompt,
- wybraną jakość generowania,
- informację o modelu GGUF,
- miejsce na LoRA i siłę LoRA,
- informację, że wynik ma wrócić jako nowa warstwa z maską.

Przykładowy format jest opisany w `workflows/inpainting/job-contract.v1.json`.

## Ważne o masce

Podstawowa droga używa `imaging.getSelection`, czyli pikselowej reprezentacji zaznaczenia Photoshopa. To jest właściwy kierunek dla jakości, bo maska może zachować nieregularny kształt i miękkie krawędzie.

Jeśli dana wersja Photoshopa odmówi odczytu maski przez Imaging API, panel zatrzyma zadanie z jasnym błędem. Nie tworzymy już prostokątnej maski awaryjnej, bo taka maska może dać twarde, sztuczne krawędzie.

## Workflow ComfyUI

Panel ma już kod do wysłania `/prompt`, ale wymaga dwóch prawdziwych plików:

- `photoshop_plugin/workflows/inpainting-api.json`,
- `photoshop_plugin/workflows/inpainting-api.mapping.json`.

W repo są tylko pliki `.example.json`. One pokazują kształt, ale nie są gotowym workflow.

Prawdziwy workflow musi wskazać:

- nazwę uploadowanego obrazu,
- nazwę uploadowanej maski,
- prompt,
- bazowy model GGUF,
- opcjonalne LoRA i ich siłę.

Przed pierwszym właściwym generowaniem kliknij `Sprawdź gotowość`. Ten przycisk nie tworzy obrazu, tylko sprawdza:

- czy jest prompt,
- czy Photoshop ma aktywny dokument i zaznaczenie,
- czy ComfyUI odpowiada,
- czy workflow i mapping można odczytać,
- czy lokalne ComfyUI ma wszystkie wymagane node'y.

Panel rozumie dwie formy LoRA:

- jedna LoRA: `style.safetensors`,
- kilka LoRA: każda w osobnej linii albo po przecinku, na przykład `style.safetensors:0.8, detail.safetensors:0.6`.

Jeśli mapping ma sekcję `inputs.loras`, panel podstawia kolejne LoRA do kolejnych slotów workflow. Starsze pola `loraName` i `loraStrength` nadal działają dla prostego workflow z jedną LoRA.

Panel przekazuje też jakość do workflow:

- `Szybki test` używa małej liczby kroków, żeby sprawdzić działanie,
- `Dobra jakość` jest domyślna,
- `Dokładna edycja` używa więcej kroków i trwa dłużej.

## Odbiór wyniku

Po wysłaniu workflow panel odpyta:

- `/history/{prompt_id}` - żeby znaleźć pliki wynikowe,
- `/view` - żeby pobrać pierwszy obraz wynikowy.

Pobrany wynik zostanie zapisany w prywatnym folderze danych wtyczki. Panel spróbuje też użyć `placeEvent`, żeby wstawić PNG do aktywnego dokumentu jako nową warstwę.

Po wstawieniu warstwy panel próbuje użyć `imaging.putLayerMask`, żeby nałożyć na wynik maskę z aktywnego zaznaczenia. Jeśli Photoshop odmówi tej operacji, panel zostawia wynik jako warstwę i zapisuje powód w `outputs.resultImage.photoshop.layerMask`.
