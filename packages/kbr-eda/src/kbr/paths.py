"""Ścieżki do danych.

Surowe dane NIE leżą w repozytorium — ani ze względu na rozmiar, ani na status
prawny. Leżą na wspólnym dysku, a każdy wskazuje na niego przez `KBR_DATA_ROOT`
w pliku `.env` (patrz `.env.example`).

Dzięki temu ten sam notebook działa u wszystkich bez podmieniania ścieżek.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(REPO_ROOT / ".env")


def data_root() -> Path:
    """Katalog główny danych na wspólnym dysku."""
    raw_value = os.environ.get("KBR_DATA_ROOT")
    if not raw_value:
        raise RuntimeError(
            "Brak zmiennej KBR_DATA_ROOT.\n"
            "Skopiuj .env.example do .env i wskaż katalog z danymi na wspólnym dysku."
        )
    root = Path(raw_value).expanduser()
    if not root.exists():
        raise FileNotFoundError(f"KBR_DATA_ROOT wskazuje na nieistniejącą ścieżkę: {root}")
    return root


def raw(*parts: str) -> Path:
    """Dane dokładnie takie, jakie dostaliśmy. Nigdy ich nie nadpisujemy."""
    return data_root() / "raw" / Path(*parts)


def interim(*parts: str) -> Path:
    """Etapy pośrednie — wolno kasować i odtwarzać z `raw`."""
    return data_root() / "interim" / Path(*parts)


def processed(*parts: str) -> Path:
    """Wynikowe zbiory gotowe do użycia przez innych (parquet / geoparquet)."""
    return data_root() / "processed" / Path(*parts)


def docs_dane(name: str) -> Path:
    """Ścieżka do opisu zbioru w repo, np. docs_dane('ankiety')."""
    return REPO_ROOT / "docs" / "dane" / f"{name}.md"


def checksum(path: Path, length: int = 12) -> str:
    """Skrócony SHA-256 pliku — do wklejenia w opis zbioru."""
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()[:length]
