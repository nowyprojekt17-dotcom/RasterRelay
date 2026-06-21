# RasterRelay — Dokument kontekstowo-decyzyjny

> **Dla każdego agenta AI:** to jest jedyne źródło prawdy o tym, co ustalono i dokąd
> zmierzamy. Przeczytaj go w całości, zanim cokolwiek zaproponujesz lub zbudujesz.
> **Aktualizuj go na bieżąco** — po każdym nowym ustaleniu, zmianie kierunku lub
> zamknięciu otwartego pytania. Dokument ma zawsze odzwierciedlać stan faktyczny.
>
> Ostatnia aktualizacja: 2026-06-21 (metodyka workflow-first)

---

## 1. Cel projektu

RasterRelay to **wtyczka do Photoshopa do lokalnego inpaintingu zaznaczonego fragmentu zdjęcia**.

Flow z perspektywy użytkownika: zaznacz obszar w Photoshopie → wpisz prompt → wtyczka
wysyła **tylko ten wycinek** do lokalnego ComfyUI → model generuje → wynik wraca w to samo
miejsce w dokumencie.

Po co to istnieje:
- Edycja **małego fragmentu dużego zdjęcia** (np. 5000×3000), nie całości — szybciej, taniej, bez niszczenia reszty.
- **W całości lokalnie** na sprzęcie użytkownika (RTX 3090 24 GB) — bez chmury, bez opłat API.

**Główne wyzwanie produktu:** wygenerowana łata **odstaje kolorem/jasnością** od reszty —
widać szew. Bezszwowe wtopienie wyniku w otoczenie to sedno jakości.

**Zasada: JEDEN przepływ, BEZ trybów.** Jeden motyw przewodni: zaznacz obszar → wpisz prompt
opisujący edycję → model wpasowuje wynik w zaznaczenie tak, by nie było widać wklejki.
Usuwanie, podmiana, zmiana koloru, domalowanie — to wszystko robi model edytujący **samym
promptem**. Nie rozbijamy tego na tryby (to sztuczna komplikacja grafu/UI). Jedyne dodatkowe
zadanie workflow poza generacją to **bezszwowe wtopienie**. Ewentualne „jak mocno wolno zmienić
obszar" to przyszły **suwak (jeden parametr)**, nie tryb — i tylko jeśli testy go wymuszą.

Launcher = narzędzie pomocnicze: odpala całe środowisko (ComfyUI + Photoshop + panel)
jednym kliknięciem, bo użytkownik jest nietechniczny.

## 2. Aktualny etap

**Faza dyskusji / projektowania.** Metodyka pracy już ustalona (patrz niżej: workflow-first).
Najpierw domykamy założenia, potem zaczynamy od workflow w ComfyUI.

### Metodyka: WORKFLOW-FIRST (zasada nadrzędna)

Kolejność prac jest odwrócona względem starego podejścia:
1. **Najpierw** budujemy działające workflow inpaintingu w ComfyUI i **iterujemy je,
   aż da zadowalające rezultaty.** To tu leży całe ryzyko i sedno jakości.
2. **Dopiero potem**, gdy workflow jest gotowe i sprawdzone, dbamy o to, żeby dało się je
   podpiąć pod launcher i wtyczkę Photoshop.

Nie budujemy launchera/wtyczki wokół niesprawdzonego workflow. Jakość udowadniamy w ComfyUI.

## 3. Ustalenia (log decyzji)

- **2026-06-21 — Reset.** Stary pipeline inpaintingu (custom nody, workflow, łańcuch koloru,
  testy, skrypty) usunięty (commit `d88835d`). Projekt zwinięty do shellu. Historia sprzed
  resetu jest w gicie.
- **2026-06-21 — Budujemy od zera.** Nowy launcher i nowa, lepiej przemyślana wtyczka.
  Obecny kod (`launcher/`, `photoshop_plugin/`) to **wyłącznie materiał referencyjny**, nie fundament.
- **2026-06-21 — Tryb pracy „B".** Odcinamy się od starych *rozwiązań* (architektura, węzły,
  UI), ale **zachowujemy zmierzone fakty** (sekcja 5) jako znane pułapki, żeby nie odkrywać ich drugi raz.
- **2026-06-21 — Sprzątanie.** Usunięte nieaktualne gałęzie `cleanup/2026-06-11`
  i `codex/fix/e2e-and-repository-hygiene`.
- **2026-06-21 — Czyszczenie ComfyUI ze starych śladów.** Usunięte z `E:\AI\ComfyUI`:
  `custom_nodes\rasterrelay_nodes` (odtwarzalny z historii git), artefakty `input\rasterrelay-*`,
  `output\RasterRelay`, runtime `%TEMP%\RasterRelay`. Dodatkowo wykryto i usunięto **cały ślad
  „ComfyBridge"** (bardzo stara wersja tego samego projektu): pakiet węzłów `comfybridge_nodes`,
  wtyczka UXP `com.comfybridge.localai`, `comfybridge-launcher` (AppData), katalogi `input\comfybridge*`.
  Uwaga: `comfybridge_nodes` nie był w repo i nie ma kopii — usunięty nieodwracalnie (autoryzowane).
- **2026-06-21 — Arsenał węzłów.** Zainstalowano 11 pakietów custom node pod jakość/maski/most
  do wtyczki (lista + opisy w `WEZLY-ARSENAL.md`). Najważniejszy: ComfyUI-Inpaint-CropAndStitch.
- **2026-06-21 — ✅ Naprawiono torch CPU.** Przyczyna: ktoś dziś ~20:29 zrobił `pip install torch==2.12.1`
  z domyślnego PyPI → wersja CPU (CUDA dla 2.12.1 nie istnieje; max cu128 to 2.11.0). Fix: rollback do
  `torch 2.11.0+cu128` + `torchvision 0.26.0+cu128` (zgodne z ocalałym `torchaudio 2.11.0+cu128`).
  Po naprawie: `torch.cuda.is_available()=True`, RTX 3090 24 GB widoczne, ComfyUI startuje (~81s).
  Usunięto też osierocony `~ransformers` i doinstalowano brakujące deps 4 wcześniejszych pakietów
  (Impact/Inspire/Crystools/SAM1: piexif, webcolors, deepdiff, segment-anything, imageio-ffmpeg).
- **2026-06-21 — ✅ Weryfikacja arsenału.** Wszystkie 11 nowych pakietów importują się czysto w ComfyUI
  (zero IMPORT FAILED). Lista + opisy: `WEZLY-ARSENAL.md`.
- **2026-06-21 — ✅ Pierwszy działający workflow (v1).** `comfy-workflows/v1-inpaint-cropstitch.json`:
  rdzeń Flux.2 Klein (ReferenceLatent edit + SetLatentNoiseMask, cfg=1, 20 kroków/euler) owinięty w
  Inpaint-Crop&Stitch (crop 1024² + kontekst 1.5×, blend 32px), **bez węzłów koloru**. Test: podmiana
  puszki Monster → granatowa puszka (`results/v1-can_00001_.png`, ~48s). Pomiar: poza maską nietknięte
  (|ΔRGB|=0.13/255), gradient na konturze res 6.27 < orig 10.40 → brak mierzalnej linii szwu. Baza Flux
  wzięta z zapisanego w ComfyUI `workflow_v0.3` (rdzeń na standardowych węzłach; stare RasterRelay* pominięte).
- **2026-06-21 — Ocena v1 (panel + metryki) → REFRAME problemu.** Szew jest rozwiązany przez sam
  crop+stitch+blend (granica niewidoczna, potwierdzone pomiarem i panelem). **Prawdziwy następny problem
  to spójność OŚWIETLENIA generowanego obiektu**, nie szew. Panel „światło/kolor": fail 7/10 — nowa
  puszka oświetlona zimno (tylko monitor), główny refleks po złej stronie, brak ciepłego bounce od
  biurka i turkusu od klawiatury. „Realizm": concern 5/10 — wieczko/pull-tab rozmyte, perspektywa elipsy,
  halucynacja tekstu „RUPNEY". „Intencja": minor 3/10 — podmiana udana, ale kolor wyszedł czarny zamiast
  granatowego. WNIOSEK: stary projekt walczył o kolor na szwie; tu szew jest za darmo z crop&stitch, a
  dźwignia jakości to dopasowanie ŚWIATŁA generowanej treści do sceny. Hipoteza v2: większy kontekst cropu
  (model „widzi" więcej sceny → lepiej dopasuje światło) + prompt na światło i „unbranded/no text".
- **2026-06-21 — Metodyka workflow-first.** Najpierw działające, sprawdzone workflow w ComfyUI,
  dopiero potem launcher i wtyczka. (szczegóły w sekcji 2)
- **2026-06-21 — Model v1: Flux Klein 9B.** Zostajemy przy nim na start. Później możliwe
  warianty workflow z innymi modelami edytującymi → nie sprzęgać grafu z Kleinem na sztywno
  bardziej niż trzeba, ale **nie budować teraz abstrakcji multi-model** (YAGNI — dopiero gdy realnie wejdzie drugi model).
- **2026-06-21 — Ocena jakości.** Ostateczny werdykt należy do użytkownika (ocena okiem).
  Agent ma **prawo i obowiązek filtrować**: nie pokazywać słabych wyników, iterować dalej i
  przynosić tylko te warte oceny. Metryki bezszwowości (np. delta szwu) służą **agentowi jako
  narzędzie triażu** „pokazać czy poprawiać", nie użytkownikowi jako kryterium.

## 4. Czego NIE robić

- Nie inspirować się starymi rozwiązaniami ani nie ciągnąć projektu w stronę poprzedniej wersji.
- Nie zaczynać kodowania, dopóki użytkownik nie powie wprost „ruszamy".
- Nie łatać starego kodu launchera/panelu — idzie do wymiany, nie do polerowania.

## 5. Znane pułapki (zmierzone fakty, nie pomysły)

Obserwacje o samym problemie/modelu — przydatne, nawet jeśli podejście się zmieni:
- Flux Klein 9B GGUF **ignoruje concat conditioning** (typu InpaintModelConditioning); reaguje
  na różnicowy denoise sterowany miękką maską.
- Łata ma **prawo różnić się od tła we wnętrzu** obiektu — korekta koloru tylko przy granicy (szwie), nie na całym wycinku.
- **Upscale małych wycinków NIE poprawia ostrości** na tym modelu (zmierzone). Generacja natywna ≤ ~1.15 MP wypada lepiej.
- Zmiany tonu są **bimodalne**: dryf modelu (<0.05) vs celowa zmiana (>0.15) — próg ~0.10 je rozdziela.
- Globalna korekta tonu (Reinhard) była nieskuteczna; działała lokalna dyfuzja tonu otoczenia do wnętrza.
- **ICC:** PNG z ComfyUI bywa bez tagu profilu → dokument roboczy w Photoshopie trzymać w sRGB.

## 6. Środowisko (stan faktyczny, do potwierdzenia przy nowym podejściu)

- ComfyUI lokalnie, `127.0.0.1:8188`.
- Modele dotychczas: `flux-2-klein-9b-Q4_K_M.gguf` (unet), `qwen_3_8b_fp8mixed.safetensors`
  (text encoder), `flux2-vae.safetensors` (vae). RTX 3090 24 GB.
- Czy zostajemy na ComfyUI + Flux Klein — **otwarte** (sekcja 7).

## 7. Otwarte pytania

### Blokujące start workflow (faza 1)
- Na jakich przypadkach testowych iterujemy (wybór z `test-images/`)? *(do ustalenia)*

### Faza 2 (po gotowym workflow)
- Co konkretnie ma być „lepiej przemyślane" w nowej wtyczce — czego brakowało/co frustrowało.
- Stack launchera: Tauri+React vs coś lżejszego.
- Podział odpowiedzialności launcher ↔ wtyczka (ile konfiguracji w panelu).

### Zamknięte
- ~~Kolejność budowy~~ → workflow-first (sekcja 2).
- ~~Model/silnik~~ → Flux Klein 9B na v1, multi-model później (sekcja 3).
- ~~Definicja „zadowalających rezultatów"~~ → werdykt użytkownika okiem, agent filtruje słabe wyniki (sekcja 3).
- ~~Skąd świeży start~~ → odwrócenie kolejności pracy na workflow-first (sekcja 2); kierunek nie wynikał z rozczarowania, tylko z lepszej metodyki.
- ~~Tryby edycji~~ → BEZ trybów; jeden przepływ sterowany promptem (sekcja 1).

## 8. Powiązane materiały

- `REBUILD.md` — szczegółowa analiza obecnego kodu jako referencji (co przejąć/odpuścić).
- `README.md` — stan repo po resecie.
- Historia gita sprzed `d88835d` — stary pipeline, gdyby trzeba coś podejrzeć.
