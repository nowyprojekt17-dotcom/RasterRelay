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

Nie dodaliśmy Tailwinda, bibliotek UI ani bibliotek ikon. Pierwszy ekran ma być możliwie prosty.
