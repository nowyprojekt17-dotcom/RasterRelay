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
- Jakie typy edycji ma obsłużyć workflow v1 (usuwanie obiektu / podmiana / domalowanie / zmiana koloru…)? *(do ustalenia)*
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

## 8. Powiązane materiały

- `REBUILD.md` — szczegółowa analiza obecnego kodu jako referencji (co przejąć/odpuścić).
- `README.md` — stan repo po resecie.
- Historia gita sprzed `d88835d` — stary pipeline, gdyby trzeba coś podejrzeć.
