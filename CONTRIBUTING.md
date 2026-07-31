# Jak pracujemy

## Rytm

- Blok pracy = 2 tygodnie, odpowiada milestone na GitHubie.
- Jedno spotkanie na blok, 30 minut, status pisemny w issue **przed** spotkaniem.
- Na spotkaniu każdy właściciel mówi jedno z trzech:
  *zrobione* / *w toku, brakuje mi X* / *nie tknąłem, oddaję zadanie*.
  Trzecia opcja jest w pełni w porządku. Milczenie przez dwa tygodnie nie jest.

## Deklaracja dostępności

Na początku każdego bloku każdy deklaruje: `0 h` / `~2 h/tydz` / `~5 h+/tydz`.
Zadań nie przypisujemy osobom, które zadeklarowały 0. Deklaracja 0 nie wymaga tłumaczenia się.

## Tablica

Kolumny: `Backlog` → `Do zrobienia` → `W toku` → `Zablokowane` → `Review` → `Zrobione`.

- Limit WIP: **maks. 5 kart** w `W toku` naraz.
- `Zablokowane` zawsze z komentarzem: na co dokładnie czekasz i od kogo.
- Karta bez właściciela nie opuszcza `Backlog`.

## Gałęzie i PR

```
dane/<krotki-opis>     np. dane/ankiety-gospodarstwa
infra/<krotki-opis>    np. infra/helper-sciezek
docs/<krotki-opis>
```

PR linkuje issue przez `Closes #N`. Review to ~20 minut czytania — reviewer nie dopisuje kodu.

## Notebooki

Nazwa: `NN_temat_inicjaly.ipynb`, np. `03_gps_predkosci_dk.ipynb`.
`NN` to numer porządkowy, nie kolejność wykonania.

Wymagania:
- notebook przechodzi od góry do dołu na czystym kernelu,
- ścieżki wyłącznie przez `kbr.paths`, nigdy bezwzględne,
- outputy nie trafiają do gita (`nbstripout` czyści je automatycznie),
- pierwsza komórka markdown: po co ten notebook istnieje i który plik `docs/dane/*.md` z niego wynika.

## Opisy zbiorów

Kopiujesz `docs/dane/_SZABLON.md` jako `docs/dane/<zbior>.md`.
Sekcja **„Czego w tych danych NIE ma"** jest obowiązkowa — to z niej powstanie lista pytań do ZDiUM.

## Decyzje

Wybory, których trzeba będzie bronić przed promotorem albo recenzentem, zapisujemy w `docs/decyzje/`.
Zakładasz issue z szablonu „Decyzja do podjęcia", po rozstrzygnięciu przenosisz treść do pliku.
Przykład takiej decyzji: czy kalibrujemy popyt na KBR 2018 czy 2024.
