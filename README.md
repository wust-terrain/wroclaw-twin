# kbr-eda

Eksploracja danych KBR Wrocław na potrzeby cyfrowego bliźniaka sieci drogowej w SUMO.

To repozytorium jest fazą rozpoznania: **czym dysponujemy, co to właściwie zawiera i czego w tym nie ma.**
Nie budujemy tu jeszcze modelu ruchu ani sterowania sygnalizacją.

## Co jest produktem tej fazy

Nie notebooki. Produktem są pliki w **`docs/dane/`** — po jednym na zbiór, wg `docs/dane/_SZABLON.md`.
Notebook jest drogą do nich i wolno go później wyrzucić. Opis zbioru zostaje i to on będzie
podstawą rozmowy z ZDiUM oraz rozdziału o danych w pracach dyplomowych.

## Start

```bash
git clone git@github.com:ORG/kbr-eda.git
cd kbr-eda

# uv: https://docs.astral.sh/uv/
uv sync --extra dev
uv run pre-commit install

cp .env.example .env
# otwórz .env i wskaż katalog z danymi na wspólnym dysku

uv run jupyter lab
```

Bez `uv` działa też `pip install -e ".[dev]"` w wirtualnym środowisku.

## Gdzie leżą dane

**Nie w repozytorium.** Surowe dane są na wspólnym dysku, ścieżkę podajesz raz w `.env`.
Powody: rozmiar plików oraz nieustalony status prawny części zbiorów (patrz issue o licencjach).

W notebookach zawsze przez helper, nigdy ścieżką bezwzględną:

```python
from kbr import paths, profile

df = pd.read_csv(paths.raw("kbr2018", "ankiety", "gospodarstwa.csv"), sep=";", encoding="cp1250")
print(profile.to_markdown(df))   # szkielet słownika kolumn do wklejenia w docs/dane/
```

Struktura na dysku:

| Katalog | Znaczenie |
|---|---|
| `raw/` | dokładnie to, co dostaliśmy — **tylko do odczytu, nigdy nie nadpisujemy** |
| `interim/` | etapy pośrednie, wolno kasować i odtworzyć z `raw/` |
| `processed/` | zbiory gotowe dla reszty zespołu (parquet / geoparquet) |

## Struktura repo

```
.github/ISSUE_TEMPLATE/   szablony zadań
docs/dane/                inwentarz danych — właściwy produkt tej fazy
docs/decyzje/             zapisane rozstrzygnięcia, które trzeba będzie uzasadnić
notebooks/                NN_temat_inicjaly.ipynb
src/kbr/                  wspólne helpery (ścieżki, profilowanie kolumn)
scripts/                  jednorazowe skrypty pomocnicze
```

## Zasady, które faktycznie egzekwujemy

1. **Jedno issue = jeden zbiór = jeden właściciel + jeden reviewer.**
2. **Surowe dane nie wchodzą do gita.** `check-added-large-files` w pre-commit tego pilnuje.
3. **Notebooki commitujemy bez outputów** — `nbstripout` robi to automatycznie.
4. **Każde twierdzenie w `docs/dane/*.md` ma odsyłacz** (plik + kolumna albo strona raportu).
   Reviewer, który nie znajduje odsyłacza, zwraca zadanie.
5. **Model językowy do kodu, nie do rozumienia danych.** Wykresy, konwersje, debugowanie — proszę bardzo.
   Ustalanie, co znaczy kolumna i jak liczono wagi ekspansji — czytamy raport sami.

Szczegóły: [`CONTRIBUTING.md`](CONTRIBUTING.md).
