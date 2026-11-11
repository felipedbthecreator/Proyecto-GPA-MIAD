"""Cleaning and quality profiling for the IGAC transaction extract."""

from __future__ import annotations

from typing import Any

import pandas as pd

DATE_COLUMNS = ("fecha_radica_texto", "fecha_apertura_texto")
NUMERIC_COLUMNS = (
    "year_radica",
    "orip",
    "num_anotacion",
    "dinamica_2024",
    "cod_natujur",
    "count_a",
    "count_de",
    "predios_nuevos",
    "tiene_valor",
    "tiene_mas_de_un_valor",
    "valor",
)
TEXT_COLUMNS = ("pk", "matricula", "departamento", "municipio", "tipo_predio_zona")


def clean_transactions(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a typed copy without silently imputing invalid values."""
    data = frame.copy()
    for column in TEXT_COLUMNS:
        if column in data:
            data[column] = data[column].astype("string").str.strip()
    if "divipola" in data:
        data["divipola"] = (
            pd.to_numeric(data["divipola"], errors="coerce")
            .astype("Int64")
            .astype("string")
            .str.zfill(4)
        )
    for column in DATE_COLUMNS:
        if column in data:
            data[column] = pd.to_datetime(data[column], errors="coerce")
    for column in NUMERIC_COLUMNS:
        if column in data:
            data[column] = pd.to_numeric(data[column], errors="coerce")
    if "year_radica" in data:
        data["year_radica"] = data["year_radica"].astype("Int64")
    if "dinamica_2024" in data:
        data["dinamica_2024"] = data["dinamica_2024"].astype("Int64")
    if "tiene_valor" in data and "valor" in data:
        data["valor_valido"] = data["valor"].gt(0) & data["tiene_valor"].eq(1)
        data["valor_simbolico_o_invalido"] = data["valor"].le(0) | data["valor"].isna()
    if "pk" in data:
        data["registro_duplicado"] = data["pk"].duplicated(keep=False)
    if "matricula" in data:
        data["matricula_valida"] = data["matricula"].notna() & data["matricula"].ne("")
    if {"valor_valido", "registro_duplicado", "matricula_valida"}.issubset(data.columns):
        data["incluido_universo_modelado"] = (
            data["valor_valido"] & ~data["registro_duplicado"] & data["matricula_valida"]
        )
    return data


def profile_transactions(frame: pd.DataFrame) -> dict[str, Any]:
    """Summarize completeness, cardinality and duplicate keys."""
    key = frame["pk"] if "pk" in frame else pd.Series(dtype="string")
    return {
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "missing_by_column": frame.isna().sum().astype(int).to_dict(),
        "duplicate_rows": int(frame.duplicated().sum()),
        "duplicate_pk": int(key.duplicated().sum()),
        "unique_departments": int(frame["departamento"].nunique()) if "departamento" in frame else 0,
        "unique_municipalities": int(frame["municipio"].nunique()) if "municipio" in frame else 0,
    }
