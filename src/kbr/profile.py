"""Szkielet słownika kolumn do `docs/dane/<zbior>.md`.

Generuje *mechaniczną* część opisu: typy, braki, liczności, przykładowe
wartości. Kolumny „Jednostka", „Znaczenie" i „Uwagi" zostają puste celowo —
wypełniasz je ręcznie na podstawie raportu metodycznego. To jest ta część,
której nie oddajemy modelowi językowemu.
"""

from __future__ import annotations

import pandas as pd


def column_summary(df: pd.DataFrame, max_examples: int = 3, unique_limit: int = 200_000) -> pd.DataFrame:
    """Statystyki per kolumna."""
    rows = []
    total = len(df)
    for name in df.columns:
        series = df[name]
        n_missing = int(series.isna().sum())

        if total <= unique_limit:
            n_unique: object = int(series.nunique(dropna=True))
        else:
            n_unique = "nie liczone (duży zbiór)"

        examples = (
            series.dropna().drop_duplicates().head(max_examples).astype(str).tolist()
        )
        rows.append(
            {
                "kolumna": name,
                "typ": str(series.dtype),
                "braki_%": round(100 * n_missing / total, 2) if total else 0.0,
                "unikalnych": n_unique,
                "przyklady": ", ".join(examples),
            }
        )
    return pd.DataFrame(rows)


def to_markdown(df: pd.DataFrame, **kwargs) -> str:
    """Gotowa tabela markdown do wklejenia w opis zbioru."""
    summary = column_summary(df, **kwargs)
    header = "| Kolumna | Typ | Jednostka | Znaczenie | % braków | Unikalnych | Przykłady | Uwagi |"
    separator = "|---|---|---|---|---|---|---|---|"
    lines = [header, separator]
    for record in summary.to_dict("records"):
        examples = str(record["przyklady"]).replace("|", "\\|")
        lines.append(
            f"| `{record['kolumna']}` | {record['typ']} |  |  | "
            f"{record['braki_%']} | {record['unikalnych']} | {examples} |  |"
        )
    return "\n".join(lines)


def missing_report(df: pd.DataFrame, threshold: float = 0.5) -> pd.DataFrame:
    """Kolumny z brakami powyżej progu — kandydaci do sekcji o ograniczeniach."""
    fraction = df.isna().mean()
    flagged = fraction[fraction > threshold].sort_values(ascending=False)
    return flagged.rename("udzial_brakow").to_frame()
