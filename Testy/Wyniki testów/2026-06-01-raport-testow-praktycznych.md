# RasterRelay - raport testow praktycznych

Data: 2026-06-01

## Cel

Sprawdzic praktycznie, czy RasterRelay potrafi wyslac obraz i maske do ComfyUI, uruchomic workflow inpaintingu FLUX.2 Klein 9B GGUF i pobrac wynik.

Wazna korekta po ocenie uzytkownika: pierwsze testy sprawdzaly techniczny przeplyw, ale maski byly zle przygotowane do oceny jakosci. Twardy kwadrat w srodku obrazu nie jest dobra maska do prawdziwego inpaintingu.

## Srodowisko

- ComfyUI: `http://127.0.0.1:8188`
- GPU: NVIDIA GeForce RTX 3090
- Workflow: `photoshop_plugin/workflows/inpainting-api.json`
- Mapping: `photoshop_plugin/workflows/inpainting-api.mapping.json`
- Model bazowy: `flux-2-klein-9b-Q4_K_M.gguf`
- LoRA: nie uzyto w tych testach

## Test 1 - PNG, twarda maska w centrum

Obraz:

`Testy/Obrazy do testowania/aa0d7431-a296-464e-9b88-a4ee2e9efc89.png`

Prompt:

`replace the masked center with a clean small red ceramic cup, realistic light, preserve the rest of the image`

Ustawienia:

- steps: 8
- cfg: 4.2
- maska: bialy prostokat w srodku obrazu
- wynik: `Testy/Wyniki testów/2026-06-01-praktyczny-test-01/result.png`
- prompt_id: `ea20e713-49d8-4ae2-b577-82831a010a8c`
- czas: 78.3 s

Ocena:

Ten test byl sukcesem technicznym, bo ComfyUI przyjal obraz, maske, workflow i zwrocil wynik. Nie byl jednak dobrym testem jakosci. Maska byla zbyt twarda i ustawiona w srodku obrazu, a nie na puszce, ktora miala byc zamieniona na kubek.

Pomiar pikseli:

- srednia roznica w masce: 8.27
- srednia roznica poza maska: 0.00

Wniosek: przeplyw techniczny dziala, ale metoda testu byla bledna.

## Test 2 - JPG, twarda maska w centrum

Obraz:

`Testy/Obrazy do testowania/envato-labs-ai-da532839-090d-4b70-9e60-1ed61c2e94a5.jpg`

Prompt:

`replace the masked center with a small clean red ceramic cup on a table, realistic, preserve the rest of the image`

Ustawienia:

- steps: 6
- cfg: 4.2
- maska: bialy prostokat w srodku obrazu
- wynik: `Testy/Wyniki testów/2026-06-01-praktyczny-test-02-jpg/result.png`
- prompt_id: `9c713f1f-727a-4fb2-a188-11632eecc0a7`
- czas: 48.2 s

Ocena:

Ten test rowniez przeszedl technicznie, ale byl slaby jako test uzytkowy. Maska byla sztuczna, twarda i nie sprawdzala prawdziwego przypadku: edycji konkretnego obiektu.

Pomiar pikseli:

- srednia roznica w masce: 8.16
- srednia roznica poza maska: 1.33

Wniosek: workflow odpowiada, ale taki test nie wystarcza do oceny jakosci inpaintingu.

## Test 3 - PNG, maska na puszce, ale jeszcze binarna

Obraz:

`Testy/Obrazy do testowania/aa0d7431-a296-464e-9b88-a4ee2e9efc89.png`

Prompt:

`replace only the can in the masked area with a small red ceramic mug held in the hand, preserve the hand, body, text and the rest of the image`

Ustawienia:

- steps: 14
- cfg: 5.0
- maska: elipsa ustawiona na puszce trzymanej w rece
- wazna korekta: po dodatkowym sprawdzeniu maska okazala sie binarna, czyli miala tylko wartosci 0 i 255
- wynik: `Testy/Wyniki testów/2026-06-01-praktyczny-test-03-puszka-soft-mask/result.png`
- maska: `Testy/Wyniki testów/2026-06-01-praktyczny-test-03-puszka-soft-mask/mask-can-soft.png`
- prompt_id: `8ae7eee6-f367-46c9-ab91-03c818b5399b`
- czas: 99.2 s

Ocena:

Ten test byl lepszy od testu 1, bo maska trafila w puszke, czyli w prawdziwy obiekt do zmiany. Po sprawdzeniu histogramu maski wyszlo jednak, ze nie byla faktycznie miekka. To znaczy: poprawilismy celowanie, ale nie naprawilismy jeszcze krawedzi.

Pomiar pikseli:

- srednia roznica w masce: 23.17
- srednia roznica poza maska: 0.00

Wniosek: po poprawieniu polozenia maski workflow zachowal sie lepiej. Ten test nie moze jednak byc dowodem na miekkie przejscia.

## Test 4 - PNG, prawdziwa miekka maska na puszce

Obraz:

`Testy/Obrazy do testowania/aa0d7431-a296-464e-9b88-a4ee2e9efc89.png`

Prompt:

`replace only the can in the masked area with a small red ceramic mug held in the hand, preserve the hand, body, face, text and the rest of the image`

Ustawienia:

- steps: 14
- cfg: 5.0
- maska: miekka elipsa ustawiona na puszce trzymanej w rece
- promien wtapiania: okolo 36 px
- poziomy szarosci w masce: 255 poziomow, od 1 do 255
- wynik: `Testy/Wyniki testów/2026-06-01-praktyczny-test-04-puszka-real-soft-mask/result.png`
- maska: `Testy/Wyniki testów/2026-06-01-praktyczny-test-04-puszka-real-soft-mask/mask-can-real-soft.png`
- prompt_id: `a4d24f42-3e77-45c8-9b5f-756f42fab5f4`
- czas: 99.3 s

Ocena:

To jest poprawiony test po uwadze uzytkownika. Maska jest ustawiona na puszce, a jej krawedz jest naprawde wtopiona. Wynik wizualnie zamienia puszke na czerwony kubek. Poza maska obraz nie zostal zmieniony.

Pomiar pikseli:

- srednia roznica w centrum maski: 25.51
- srednia roznica na miekkiej krawedzi: 1.62
- srednia roznica poza maska: 0.00

Wniosek: to potwierdza, ze dobra maska musi miec dwa warunki naraz: trafiac w obiekt i miec miekkie przejscie.

## Naprawione bledy

1. Twarde maski w pliku wysylanym do ComfyUI

   Plugin zaczal zmiekczac maske przed wyslaniem jej do ComfyUI. To zmniejsza ryzyko widocznej, ostrej granicy miedzy edytowanym miejscem a reszta obrazu.

2. Twarda maska warstwy wynikowej w Photoshopie

   Panel nie przekazuje juz surowej, ostrej selekcji bezposrednio do maski warstwy. Tworzy miekka wersje maski i dopiero ja naklada na warstwe wynikowa przez Photoshop Imaging API.

3. Zle ustawiony test praktyczny

   Test z kubkiem zostal powtorzony z maska ustawiona na puszce, a nie z kwadratem w srodku obrazu.

4. Zla interpretacja pierwszego wyniku

   Pierwszy test zostaje w raporcie jako dowod, ze przeplyw techniczny dziala, ale nie jako dowod, ze jakosc inpaintingu jest dobra.

## Nadal do dopiecia

- Launcher powinien dostac proste ustawienie typu `Wtapianie maski`, najlepiej z domyslna wartoscia automatyczna.
- Testy jakosci powinny zawsze uzywac maski na konkretnym obiekcie, nie losowego prostokata.
- Trzeba jeszcze wykonac reczny test w Photoshop Beta 27.8, z prawdziwym zaznaczeniem i wynikiem jako warstwa z miekka maska.

## Wniosek

Rdzen techniczny dziala. Najwazniejsza poprawka jakosciowa na tym etapie to nie tylko lepsze parametry workflow, ale poprawne maski: miekka krawedz i precyzyjne trafienie w obiekt.
