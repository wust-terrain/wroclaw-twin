# Ten katalog jest celowo pusty

Dane leżą na wspólnym dysku, nie w repozytorium.

Powody:
1. rozmiar — repo z gigabajtami CSV staje się bezużyteczne,
2. status prawny — dopóki nie mamy potwierdzonych licencji, nic nie publikujemy.

Ścieżkę do wspólnego dysku ustawiasz raz w pliku `.env` (patrz `.env.example`),
a w kodzie sięgasz przez `kbr.paths.raw()` / `interim()` / `processed()`.

Manifest z sumami kontrolnymi każdego zbioru trzymamy w `docs/dane/<zbior>.md`,
sekcja „Lokalizacja i format". Dzięki temu wiadomo, czy wszyscy pracują na tej samej wersji pliku.
