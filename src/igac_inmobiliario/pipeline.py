"""Command-line pipeline for sample or complete scoped extraction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .api import SocrataClient
from .cleaning import clean_transactions, profile_transactions
from .scope import ANALYSIS_COLUMNS, build_scope_where


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--full", action="store_true", help="download all scoped rows")
    mode.add_argument("--sample-size", type=int, help="download at most this many rows")
    parser.add_argument("--page-size", type=int, default=5_000)
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    args = parser.parse_args()

    client = SocrataClient()
    where = build_scope_where()
    expected_rows = client.count(where=where)
    if args.sample_size is not None:
        raw = client.fetch(
            limit=args.sample_size,
            page_size=args.page_size,
            where=where,
            select=ANALYSIS_COLUMNS,
        )
    else:
        raw = client.fetch_all(
            where=where,
            select=ANALYSIS_COLUMNS,
            page_size=args.page_size,
            expected_rows=expected_rows,
        )
    cleaned = clean_transactions(raw)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    filename = (
        "compraventas_eje_cafetero_muestra_limpia.csv"
        if args.sample_size is not None
        else "compraventas_eje_cafetero_completo_limpio.csv"
    )
    cleaned.to_csv(args.output_dir / filename, index=False)
    (args.output_dir / "perfil_calidad.json").write_text(
        json.dumps(
            {**profile_transactions(cleaned), "expected_rows": expected_rows},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Filas descargadas y procesadas: {len(cleaned):,}")
    print(f"Resultados: {args.output_dir}")


if __name__ == "__main__":
    main()
