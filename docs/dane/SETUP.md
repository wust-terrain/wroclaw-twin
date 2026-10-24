# SETUP — środowisko i dane wejściowe

Cel: każdy członek zespołu ma **to samo środowisko i dokładnie te same dane wejściowe**, więc podział na strefy, czyszczenie OSM i siatki SUMO są porównywalne i odtwarzalne.

Dwie zasady, z których wynika reszta dokumentu:

1. **Nie pobieramy `dolnoslaskie-latest.osm.pbf` na własną rękę.** Plik `-latest` zmienia się codziennie. Wszyscy używamy jednego, zamrożonego snapshotu i weryfikujemy go sumą kontrolną.
2. **Wersja SUMO jest przypięta.** Siatka generowana przez `netconvert` zależy od jego wersji.

Instrukcja była testowana na Ubuntu 24.04. Dla innych systemów brak weryfikacji (na Windows prawdopodobnie najprościej WSL2 z Ubuntu 24.04, ale nie sprawdzaliśmy tego).

---

## 0. Zamrożone wejścia

| Element | Wartość |
|---|---|
| System | Ubuntu 24.04 |
| SUMO / `netconvert` | **1.28.0** (PPA `ppa:sumo/stable`) |
| Python | 3.12 (zarządzany przez `uv`) |
| Snapshot OSM | `data/raw/osm/dolnoslaskie_2026-10-23.osm.pbf` |
| Znacznik czasu danych (`osmosis_replication_timestamp`) | `2026-10-23T20:20:51Z` |
| Rozmiar pliku | 181 792 406 B |
| SHA-256 | `4b708241a7b9af4170e8dc2c11ba94b86154791a6d5f437b6bf27d5a5f4689db` |
| Źródło | Geofabrik, `europe/poland/dolnoslaskie` |
| Dane KBR 2018 | `23.10.2026 https://bip.um.wroc.pl/attachments/download/75769` |
| `osmium` | `1.16.0` |

Zmiana któregokolwiek wiersza to **decyzja zespołu**: zmieniamy tę tabelę w osobnym commicie i opisujemy powód w `docs/decisions.md`. Wyniki (strefy, wagi, raporty) zawsze podają, na którym snapshocie powstały.

---

## 1. Instalacja narzędzi

```bash
sudo add-apt-repository ppa:sumo/stable
sudo apt-get update
sudo apt-get install sumo sumo-tools sumo-doc osmium-tool qgis
echo 'export SUMO_HOME="/usr/share/sumo"' >> ~/.bashrc
source ~/.bashrc
curl -LsSf https://astral.sh/uv/install.sh | sh     # jeśli nie masz uv
```

Sprawdź wersje:

```bash
netconvert --version | head -1     # oczekiwane: Eclipse SUMO netconvert 1.28.0
osmium --version | head -1
uv --version
```

Jeśli PPA zaoferuje już nowszą wersję SUMO niż 1.28.0, **nie aktualizuj na własną rękę**. Sprawdź `apt-cache policy sumo` i zgłoś to zespołowi.

JOSM instalujemy dopiero na etapie czyszczenia (z oficjalnej strony projektu, bo wersje z dystrybucji bywają stare).

## 2. Repo i środowisko Python

```bash
git clone <TODO: adres repo> wroclaw-twin
cd wroclaw-twin
uv sync
mkdir -p data/raw/osm data/raw/kbr2018/points data/interim data/derived
```

`uv sync` instaluje zależności z `pyproject.toml` i `uv.lock`, więc nie używaj `uv add` bez uzgodnienia. Jeśli `pymetis` się nie zainstaluje, zgłoś to. Wybierzemy alternatywę (KaHIP albo własna implementacja na `networkx`).

`data/raw/` i `data/interim/` są w `.gitignore`. Surowych danych nie commitujemy.

## 3. Dane KBR 2018

Rozpakuj paczkę z pomiarami natężenia ruchu drogowego i skopiuj pliki:

```bash
REPO=$(pwd)
cd /sciezka/do/rozpakowanej/paczki     # katalog z plikami .xlsx i EtapV-2_Punkty_*
cp *.xlsx "$REPO/data/raw/kbr2018/"
cp EtapV-2_Punkty_pomiarowe_ruchu_drogowego.{shp,dbf,shx,prj,cpg,sbn,sbx,xml} "$REPO/data/raw/kbr2018/points/"
cd "$REPO/data/raw/kbr2018"
mv *ring\ 1.xlsx ring1.xlsx
mv *ring\ 2.xlsx ring2.xlsx
mv *ring\ 3.xlsx ring3.xlsx
cd "$REPO"
```

Nazwy plików w oryginalnej paczce mają wadliwe kodowanie polskich znaków. Dlatego rename na ASCII jest obowiązkowy dla trzech plików ringów, bo skrypty odwołują się do `ring1.xlsx`, `ring2.xlsx` i `ring3.xlsx`. Pozostałe pliki xlsx zostaw bez zmian.

Układ współrzędnych shapefile to ETRF2000-PL / CS2000/18 (EPSG:2177). Biblioteka `geopandas` nie odczytuje go automatycznie z `.prj`, więc skrypty ustawiają go jawnie.

## 4. Snapshot OSM

**Opcja A (próbujemy najpierw): plik z datą w nazwie na Geofabrik.** Serwer trzyma też pliki z datą w nazwie, ale nie na stałe:

```bash
cd data/raw/osm
curl -LO https://download.geofabrik.de/europe/poland/dolnoslaskie-261023.osm.pbf
mv dolnoslaskie-261023.osm.pbf dolnoslaskie_2026-10-23.osm.pbf
cd ../../..
```

Jeśli dostaniesz 404 albo suma kontrolna (poniżej) się nie zgodzi, przejdź do opcji B.

**Opcja B: kopia zespołu.** Pobierz plik `dolnoslaskie_2026-10-23.osm.pbf` z `https://drive.google.com/file/d/1bnzrQAgaZxDZa6urcRYAaz0iTsWHokj9/view?usp=drive_link` i umieść w `data/raw/osm/`.

**Weryfikacja (obowiązkowa):**

```bash
echo "4b708241a7b9af4170e8dc2c11ba94b86154791a6d5f437b6bf27d5a5f4689db  data/raw/osm/dolnoslaskie_2026-10-23.osm.pbf" | sha256sum -c
osmium fileinfo data/raw/osm/dolnoslaskie_2026-10-23.osm.pbf | grep osmosis_replication_timestamp
```

Oczekiwane: `OK` oraz `osmosis_replication_timestamp=2026-10-23T20:20:51Z`. Przy innym wyniku **nie kontynuuj** i nie pobieraj `-latest` jako zamiennika.

## 5. Wycinek OSM dla RING 1–3

Wycinek jest produktem pochodnym zamrożonego pliku (można go w każdej chwili wyciąć od nowa), dlatego nie wersjonujemy go w gicie. Obszar to ramka obejmująca punkty `R1`–`R3` z KBR plus margines ok. 3 km.

```bash
BBOX=$(uv run python src/00_kbr_points.py)
echo "$BBOX"
osmium extract --bbox "$BBOX" --strategy complete_ways \
  data/raw/osm/dolnoslaskie_2026-10-23.osm.pbf -o data/interim/wroclaw_r123.osm.pbf
```

Skrypt `src/00_kbr_points.py` konwertuje punkty KBR do `data/interim/kbr_points.gpkg` i drukuje bbox w formacie `W,S,E,N`.

Oczekiwany bbox: `<TODO: uzupełnić po uruchomieniu>`.

Szybka kontrola wycinka:

```bash
osmium fileinfo -e data/interim/wroclaw_r123.osm.pbf
osmium tags-filter data/interim/wroclaw_r123.osm.pbf n/highway=traffic_signals \
  -o /tmp/ts.osm.pbf --overwrite && osmium fileinfo -e /tmp/ts.osm.pbf
```

Oczekiwana liczba węzłów `highway=traffic_signals` w wycinku: `<TODO: uzupełnić po uruchomieniu>`. U każdego powinna wyjść identyczna. Bajtowa zgodność wycinka zależy od wersji `osmium`, więc porównujemy liczby, nie sumy kontrolne.

## 6. Test dymny SUMO

Sprawdza, że narzędzia działają razem, na małym obszarze w centrum:

```bash
osmium extract --bbox 17.015,51.095,17.055,51.12 data/interim/wroclaw_r123.osm.pbf \
  -o /tmp/test.osm.pbf --overwrite
osmium cat /tmp/test.osm.pbf -o /tmp/test.osm --overwrite
netconvert --osm-files /tmp/test.osm -o /tmp/test.net.xml
```

Opcje `netconvert` są tu domyślne i służą wyłącznie testowi. Parametry modelu ustalimy osobno i zapiszemy w `docs/decisions.md`.

## 7. Lista kontrolna

- [ ] `netconvert --version` → 1.28.0
- [ ] SHA-256 snapshotu OSM się zgadza
- [ ] `osmosis_replication_timestamp` = `2026-10-23T20:20:51Z`
- [ ] `uv sync` bez błędów
- [ ] bbox wycinka i liczba `traffic_signals` zgodne z wartościami z sekcji 5
- [ ] test dymny SUMO kończy się utworzeniem `/tmp/test.net.xml`

## 8. Rozwiązywanie problemów

- **404 na Geofabrik.** Plik z datą mógł już zniknąć z serwera. Użyj opcji B.
- **Rozbieżna suma kontrolna.** Nie używaj pliku. Pobierz ponownie albo skorzystaj z kopii zespołu.
- **`sumo-gui` lub `netedit` nie startuje.** Zdarza się pod Waylandem. Spróbuj sesji X11. Do podziału na strefy GUI nie jest potrzebne.
- **Dziwne nazwy plików KBR (mojibake).** Wykonaj rename z sekcji 3.