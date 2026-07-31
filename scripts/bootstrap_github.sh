#!/usr/bin/env bash
# Jednorazowy bootstrap: etykiety + startowy backlog.
#
# Wymaga GitHub CLI (https://cli.github.com) i `gh auth login`.
# Użycie:
#   REPO=moja-org/kbr-eda ./scripts/bootstrap_github.sh
#
# Skrypt jest idempotentny dla etykiet, ale NIE dla issue — odpal go raz.

set -euo pipefail

REPO="${REPO:?Ustaw REPO, np. REPO=moja-org/kbr-eda}"

echo "==> Etykiety"
add_label() {
  gh label create "$1" --repo "$REPO" --color "$2" --description "$3" --force >/dev/null
  echo "    $1"
}

add_label "dane"            "0E8A16" "Analiza konkretnego zbioru danych"
add_label "infra"           "5319E7" "Kod, środowisko, konfiguracja repo"
add_label "decyzja"         "D93F0B" "Rozstrzygnięcie do uzasadnienia na zewnątrz"
add_label "dane:ankiety"    "C2E0C6" "Ankiety w gospodarstwach domowych"
add_label "dane:bigdata"    "C2E0C6" "Dane operatora komórkowego / więźby"
add_label "dane:gps"        "C2E0C6" "Prędkości i trace'y GPS"
add_label "dane:natezenia"  "C2E0C6" "Pomiary natężeń ruchu"
add_label "dane:geo"        "C2E0C6" "Shapefile, rejonizacja, warstwy przestrzenne"
add_label "blokuje"         "B60205" "Blokuje inne zadania — priorytet"
add_label "czeka"           "FBCA04" "Zablokowane, czekamy na coś z zewnątrz"

echo "==> Startowy backlog"
new_issue() {
  local title="$1" labels="$2" body="$3"
  gh issue create --repo "$REPO" --title "$title" --label "$labels" --body "$body" >/dev/null
  echo "    $title"
}

new_issue "[infra] Wspólne środowisko i konwencje ładowania danych" "infra,blokuje" \
"Blokuje wszystkie zadania z danymi — robimy to pierwsze.

**Zakres:** pyproject + lock, \`kbr.paths\`, \`kbr.profile\`, pre-commit z nbstripout, .env.example.
**Nie wchodzi:** CI, testy, Docker.

**DoD**
- [ ] Druga osoba klonuje repo od zera i odpala szablonowy notebook bez pytań
- [ ] Instrukcja w README działa dosłownie, linijka po linijce"

new_issue "[dane] Ankiety w gospodarstwach domowych — profile podróży wg grup" "dane,dane:ankiety" \
"Kto, w jakiej grupie, czym, skąd i dokąd jeździ.

**Zależności:** issue infra.

**Uwaga:** przed jakąkolwiek agregacją ustal, jak policzono wagi ekspansji.
Liczby policzone bez zrozumienia wag są nie do obrony.

**DoD:** \`docs/dane/ankiety.md\` wg szablonu + notebook."

new_issue "[dane] Więźby z big data (SIM) — macierze OD, lokalne vs regionalne" "dane,dane:bigdata" \
"Macierze przestrzenne skąd–dokąd z danych operatora komórkowego.

**Do opisania obowiązkowo w sekcji o ograniczeniach:**
- reprezentatywność demograficzna udziału rynkowego operatora,
- rozdzielczość przestrzenna ograniczona zasięgiem BTS (w centrum grubo powyżej skali skrzyżowania),
- heurystyki detekcji podróży i współczynniki ekspansji zwykle nieudokumentowane.

Praktyczna konsekwencja do zweryfikowania na danych: te dane są mocne dla podróży długich
i regionalnych, słabe dla krótkich wewnątrzmiejskich. To odpowiada wprost na pytanie
o różnicę lokalne/regionalne.

**Docelowy format:** macierz OD nadająca się do \`od2trips\` + jawny opis rejonizacji."

new_issue "[dane] Prędkości GPS a sieć OSM — rozpoznanie przed map matchingiem" "dane,dane:gps" \
"**To zadanie jest rozpoznaniem, nie implementacją.** Zanim ktokolwiek zacznie map matching,
ustalamy, co właściwie dostaliśmy.

Do ustalenia:
1. Czy mamy surowe trace'y GPS, czy prędkości już zagregowane do odcinków?
   - surowe trace'y → map matching (\`leuvenmapmatching\`, \`mappymatch\`, Valhalla Meili, OSRM /match)
   - zagregowane → są na sieci wykonawcy, nie na OSM; potrzebny join przestrzenny sieć↔OSM
     (bufor + zgodność kierunku + odległość Frécheta) — istotnie trudniejsze, niż brzmi
2. Jaka jest rozdzielczość czasowa i czy da się rozdzielić godziny szczytu od pozaszczytowych.

**Ostrzeżenie metodyczne do zapisania w opisie zbioru:**
w SUMO atrybut \`speed\` na krawędzi to prędkość swobodna, a nie średnia obserwowana.
Opóźnienia od zatłoczenia i sygnalizacji emergują z symulacji. Wstawienie zmierzonych
prędkości średnich policzy opóźnienie podwójnie.
- prędkość swobodna (percentyl 85 albo mediana poza szczytem) → \`speed\` krawędzi / kalibracja \`speedFactor\`
- prędkości szczytowe → **target walidacyjny**, nie input

**DoD:** \`docs/dane/gps.md\` + rekomendacja narzędzia + oszacowanie nakładu na właściwy map matching."

new_issue "[dane] Pomiary natężeń — z Excela do formatu maszynowego" "dane,dane:natezenia" \
"**DoD:** CSV z lokalizacją (współrzędne, nie opis słowny), kierunkiem, interwałem agregacji
i typem pojazdu + \`docs/dane/natezenia.md\`.

Sprawdź, czy to natężenia na przekroju, czy relacje skrętne — dla sterowania sygnalizacją
to zupełnie różne dane.

Docelowa ścieżka wykorzystania w SUMO: \`routeSampler.py\` (dopasowanie rozkładu tras do zliczeń)."

new_issue "[dane] Shapefile rejonizacji — geometria stref" "dane,dane:geo" \
"Warstwa mapująca rejony komunikacyjne — definiuje granulację macierzy OD.

Ścieżka do SUMO: \`polyconvert\` → \`edgesInDistricts.py\` (z \`sumo/tools/district/\`) generuje
definicje TAZ z sieci i poligonów.

**DoD:** rejony wczytane, zwizualizowane, policzone, mapowanie rejon → obszar w sieci + \`docs/dane/rejonizacja.md\`."

new_issue "[dane] Luka: czego KBR nie zawiera, a potrzebuje sterowanie sygnalizacją" "dane,blokuje" \
"KBR to badanie **popytu**. Sterowanie sygnalizacją potrzebuje czegoś innego.

Spisz, czego brakuje — kandydaci do sprawdzenia:
- geometria wlotów, pasów i relacji skrętnych,
- aktualne programy sygnalizacji (baseline GERTRUDE),
- dane z detekcji,
- rozkłady tramwajowe i zasady priorytetu.

Ta lista jest szkieletem pierwszego zapytania do ZDiUM. Pierwsze wrażenie robimy raz —
im konkretniejsza lista, tym poważniej nas potraktują.

**DoD:** \`docs/dane/luka-tsc.md\` + wstępny szkic zapytania."

new_issue "[decyzja] Kalibrujemy popyt na KBR 2018 czy KBR 2024?" "decyzja" \
"KBR 2018 jest sprzed pandemii. KBR 2024 (trzecia edycja, marzec–czerwiec 2024, wyniki
opublikowane w grudniu 2024) pokazuje istotnie inną strukturę podróży — udział samochodu
wśród wrocławian spadł po raz pierwszy poniżej 40%.

Argument za 2018: szerszy komponent big data (przemieszczenia kart SIM dla ruchu ogółem,
21 gmin) wobec 2024 (big data ograniczone do pojazdów dostawczych i ciężarowych, 9 gmin).
Do zweryfikowania w raportach, nie na podstawie doniesień prasowych.

To pytanie padnie od promotora albo od ZDiUM. Potrzebujemy zapisanej odpowiedzi,
nie domyślnego wyboru.

**DoD:** wpis w \`docs/decyzje/\` z uzasadnieniem i jawnie nazwanym ograniczeniem,
które odtąd deklarujemy w pracach."

new_issue "[decyzja] Status prawny i licencje zbiorów" "decyzja,czeka" \
"Dla każdego zbioru: co wolno opublikować w pracy dyplomowej i artykule, a co wolno
wrzucić do publicznego repozytorium. Dane pochodne od operatora komórkowego i GPS
mogą mieć inne warunki niż reszta.

Do rozstrzygnięcia **zanim** cokolwiek trafi do publicznego repo.

**DoD:** tabela zbiór → źródło → licencja → co wolno, w \`docs/decyzje/\`."

echo
echo "Gotowe. Utwórz teraz Project (Board) i wciągnij issue:"
echo "  Kolumny: Backlog / Do zrobienia / W toku / Zablokowane / Review / Zrobione"
echo "  Limit WIP w kolumnie 'W toku': 5"
