"""Cleaning and quality profiling for the IGAC transaction extract."""

from __future__ import annotations

from typing import Any

import pandas as pd

DATE_COLUMNS = ("fecha_radica_texto", "fecha_apertura_texto")
NUMERIC_COLUMNS = ("year_radica","orip","num_anotacion","dinamica_2024","cod_natujur","count_a","count_de","predios_nuevos","tiene_valor","tiene_mas_de_un_valor","valor",)
TEXT_COLUMNS = ("pk","matricula","departamento","municipio","tipo_predio_zona","documento_justificativo",)

def extraer_fecha_escritura(documento: pd.Series) -> pd.Series:
    """Extrae la fecha de la escritura del texto del documento justificativo.
    """
    partes = documento.astype("string").str.extract(r"\bDEL?\s+(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
    anio = pd.to_numeric(partes[2], errors="coerce")
    anio = anio.where(anio >= 100, anio + 2000)
    anio = anio.where(anio <= 2030, anio - 100)
    texto = (
        anio.astype("Int64").astype("string")
        + "-" + partes[1].str.zfill(2)
        + "-" + partes[0].str.zfill(2)
    )
    return pd.to_datetime(texto, format="%Y-%m-%d", errors="coerce")

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
        data["registro_duplicado"] = data["pk"].duplicated(keep="first")
    if {"documento_justificativo", "year_radica"}.issubset(data.columns):
        data["fecha_escritura"] = extraer_fecha_escritura(data["documento_justificativo"])
        brecha = data["year_radica"] - data["fecha_escritura"].dt.year
        data["radicacion_antes_de_escritura"] = brecha.lt(0).fillna(False).astype(bool)
        if {"matricula", "num_anotacion"}.issubset(data.columns):
            # La misma anotación puede aparecer en varios años. Se conserva la copia
            # coherente con la escritura (año >= año de la escritura, lo más cercano);
            # si ninguna lo es, la menos distante. Las demás se marcan como duplicadas.
            prioridad = pd.DataFrame(
                {"brecha_negativa": brecha.lt(0).fillna(True).astype(bool),
                    "brecha_abs": brecha.abs(),
                    "anio": data["year_radica"],},index=data.index,)
            orden = prioridad.sort_values(
                ["brecha_negativa", "brecha_abs", "anio"], na_position="last").index
            data["anotacion_duplicada"] = (
                data.loc[orden]
                .duplicated(["matricula", "num_anotacion"], keep="first")
                .reindex(data.index))
    if "matricula" in data:
        data["matricula_valida"] = data["matricula"].notna() & data["matricula"].ne("")
    if {"valor_valido", "registro_duplicado", "matricula_valida"}.issubset(data.columns):
        data["incluido_universo_modelado"] = (data["valor_valido"] & ~data["registro_duplicado"] & data["matricula_valida"])
        if "anotacion_duplicada" in data:
            data["incluido_universo_modelado"] &= ~data["anotacion_duplicada"]
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
