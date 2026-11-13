"""Command-line pipeline for sample or complete scoped extraction."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .api import SocrataClient
from .cleaning import clean_transactions, profile_transactions
from .scope import ANALYSIS_COLUMNS, build_scope_where

RAW_DIR = Path("data/raw")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--full", action="store_true", help="download all scoped rows")
    mode.add_argument("--sample-size", type=int, help="download at most this many rows")
    parser.add_argument(
        "--desde-raw",
        action="store_true",
        help="no descarga: vuelve a limpiar la última descarga guardada en data/raw",
    )
    parser.add_argument("--page-size", type=int, default=5_000)
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    args = parser.parse_args()

    tipo = "muestra" if args.sample_size is not None else "completo"
    raw_path = RAW_DIR / f"compraventas_eje_cafetero_{tipo}_crudo.csv"
    meta_path = RAW_DIR / f"compraventas_eje_cafetero_{tipo}_descarga.json"

    if args.desde_raw:
        # Re-limpieza sin internet: todo se lee como texto, igual que llega de la API.
        if not raw_path.exists():
            raise SystemExit(f"No existe {raw_path}. Primero haz una descarga.")
        raw = pd.read_csv(raw_path, dtype=str, keep_default_na=False, na_values=[""])
        descarga = json.loads(meta_path.read_text(encoding="utf-8"))
        print(f"Re-limpiando la descarga del {descarga['fecha_descarga_utc']} (sin internet)")
    else:
        client = SocrataClient()
        meta = client.metadata()
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
        # Trazabilidad (Entrega 2, paso 1): cuándo se descargó y qué versión del portal.
        actualizado = meta.get("rowsUpdatedAt")
        descarga = {
            "fecha_descarga_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "portal_actualizado_utc": (
                datetime.fromtimestamp(actualizado, tz=timezone.utc).isoformat(timespec="seconds")
                if actualizado
                else None
            ),
            "dataset": meta.get("name"),
            "filtro": where,
            "filas_esperadas": expected_rows,
            "filas_descargadas": int(len(raw)),
        }
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        raw.to_csv(raw_path, index=False)
        meta_path.write_text(json.dumps(descarga, ensure_ascii=False, indent=2), encoding="utf-8")

    cleaned = clean_transactions(raw)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    filename = (
        "compraventas_eje_cafetero_muestra_limpia.csv"
        if tipo == "muestra"
        else "compraventas_eje_cafetero_completo_limpio.csv"
    )
    cleaned.to_csv(args.output_dir / filename, index=False)
    (args.output_dir / f"perfil_calidad_{tipo}.json").write_text(
        json.dumps(
            {**profile_transactions(cleaned), "descarga": descarga},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"Filas procesadas: {len(cleaned):,}")
    print(f"Resultados: {args.output_dir}")


if __name__ == "__main__":
    main()