# <Nazwa zbioru>

> Skopiuj ten plik jako `docs/dane/<nazwa_zbioru>.md` i wypełnij.
> To jest właściwy produkt zadania — notebook jest tylko drogą do niego.
> **Każde twierdzenie tutaj musi mieć odsyłacz**: nazwa pliku i kolumny albo numer strony w raporcie.
> Jeśli czegoś nie wiesz — napisz „nieustalone", nie zgaduj.

| | |
|---|---|
| **Właściciel** | @nick |
| **Reviewer** | @nick |
| **Ostatnia aktualizacja** | RRRR-MM-DD |
| **Powiązane issue** | #N |

## 1. Pochodzenie

- **Badanie / źródło:** (np. KBR 2018, komponent „ankiety w gospodarstwach domowych")
- **Wykonawca:** 
- **Rok zbierania danych:** 
- **Skąd to mamy:** (URL BIP / kontakt / przekazane przez)
- **Status prawny:** licencja, czy wolno publikować, czy wolno wrzucić do publicznego repo → patrz issue o licencjach

## 2. Lokalizacja i format

| Plik | Format | Rozmiar | Kodowanie | SHA-256 (pierwsze 12 znaków) |
|---|---|---|---|---|
| `raw/.../plik.csv` | CSV, separator `;` | 40 MB | cp1250 | `a1b2c3d4e5f6` |

## 3. Co to właściwie jest

- **Jednostka obserwacji:** co reprezentuje jeden wiersz? (osoba? podróż? etap podróży? pojazd? godzina na przekroju?)
- **Liczba wierszy:** 
- **Zakres czasowy:** 
- **Zakres przestrzenny:** (Wrocław? + ile gmin? jaka rejonizacja?)
- **Rozdzielczość czasowa:** (doba? godzina? 15 minut?)
- **Rozdzielczość przestrzenna:** (rejon komunikacyjny? punkt pomiarowy? odcinek sieci?)

## 4. Słownik kolumn

| Kolumna | Typ | Jednostka | Znaczenie | % braków | Uwagi |
|---|---|---|---|---|---|
| | | | | | |

Wygenerowany szkielet tej tabeli: `kbr.profile.column_summary(df)`.
Kolumnę „Znaczenie" wypełniasz ręcznie na podstawie raportu metodycznego — to jest ta część, której nie oddajemy modelowi.

## 5. Jak te dane powstały

- **Sposób zbierania:** (wywiad w gospodarstwie? aplikacja mobilna? kamera? BTS?)
- **Wielkość i dobór próby:** 
- **Ważenie / ekspansja:** czy w danych są wagi? jak policzone? czy udokumentowane?
- **Preprocessing wykonawcy:** co już zostało przetworzone, zanim to dostaliśmy?

## 6. Znane obciążenia i ograniczenia

Konkretnie, nie ogólnikami. Przykłady rzeczy, które tu należą:
- reprezentatywność próby względem struktury demograficznej
- rozdzielczość przestrzenna gorsza, niż sugeruje format zapisu
- brakujące okresy, dni, lokalizacje
- nieudokumentowane heurystyki wykonawcy
- wiek danych względem dzisiejszego stanu sieci i zachowań komunikacyjnych

## 7. Czego w tych danych NIE ma

**Sekcja obowiązkowa.** To ona zbuduje listę pytań do ZDiUM i uchroni nas przed obiecaniem czegoś, czego nie da się zrobić.

## 8. Przydatność dla projektu

- **Nadaje się do:** 
- **Nie nadaje się do:** 
- **Wymaga uzupełnienia o:** 

## 9. Odsyłacze

- Raport metodyczny, s. XX–YY
- Notebook: `notebooks/NN_temat_inicjaly.ipynb`
