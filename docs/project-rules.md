# Zasady pracy nad RasterRelay

Ten projekt ma być prosty do zrozumienia, spokojny w rozwoju i gotowy na dalszą pracę.

## Najważniejsze zasady

- Nie budujemy wszystkiego naraz.
- Każdy etap ma być mały i możliwy do sprawdzenia.
- Repozytorium ma być schludne, opisane i logiczne.
- Kod ma być prosty, czytelny i bez niepotrzebnych sztuczek.
- Ważne decyzje techniczne zapisujemy w dokumentacji.
- Nie dodajemy bibliotek przypadkowo.
- LoRA są częścią podstawowego projektu, nie dodatkiem na później.

## Co oznacza MVP

Pierwszy produkt minimalny skupia się na jednej funkcji: Inpainting Brush Tool.

Docelowy przepływ:

1. Photoshop ma obraz i zaznaczenie.
2. Użytkownik wpisuje prompt.
3. RasterRelay używa modelu bazowego GGUF.
4. Użytkownik może użyć jednej albo kilku LoRA.
5. Wynik wraca jako nowa warstwa z maską.
6. Oryginalna warstwa zostaje nienaruszona.

Na pierwszym etapie budujemy tylko fundament: Launcher i ekran gotowości.
