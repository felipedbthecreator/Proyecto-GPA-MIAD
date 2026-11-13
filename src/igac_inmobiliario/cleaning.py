"""Cleaning and quality profiling for the IGAC transaction extract."""

from __future__ import annotations

from typing import Any

import pandas as pd

DATE_COLUMNS = ("fecha_radica_texto", "fecha_apertura_texto")
NUMERIC_COLUMNS = ("year_radica","orip","num_anotacion","dinamica_2024","cod_natujur","count_a","count_de","predios_nuevos","tiene_valor","tiene_mas_de_un_valor","valor",)
# Valor simbólico (Entrega 2: "inferior a un mínimo por municipio"). Umbrales calibrados
# con la distribución observada en compraventas individuales y contemporáneas.
UMBRAL_VALOR_ABSURDO = 100_000        # pesos: ningún inmueble se transa por menos
FRACCION_MEDIANA_SIMBOLICO = 0.01     # menos del 1% de la mediana de su municipio-año
MIN_REGISTROS_CELDA = 20              # mínimo de registros para usar la mediana municipio-año
TEXT_COLUMNS = ("pk","matricula","departamento","municipio","tipo_predio_zona","documento_justificativo",)

def extraer_fecha_escritura(documento: pd.Series) -> pd.Series:
    """Extrae la fecha de la escritura del texto del documento justificativo.
    """
    partes = documento.astype("string").str.extract(r"\bDEL?\s+(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
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
            .str.zfill(5)
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
        data["rezago_escritura_anios"] = brecha.astype("Int64")
        data["escritura_rezagada"] = brecha.ge(2).fillna(False).astype(bool)
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
    if {"documento_justificativo", "orip", "matricula", "fecha_escritura", "valor"}.issubset(data.columns):
        # Escritura paquete: una misma escritura (oficina + número + fecha) sobre varios folios.
        # La llave no usa el texto completo porque cambia de formato entre copias.
        numero = data["documento_justificativo"].str.extract(r"ESCRITURA\s+0*(\d+)")[0]
        clave = (
            data["orip"].astype("Int64").astype("string")
            + "|" + numero
            + "|" + data["fecha_escritura"].dt.strftime("%Y-%m-%d")
        )
        data["clave_escritura"] = clave.astype("string")
        grupo = data.groupby(clave)
        folios = grupo["matricula"].transform("nunique")
        data["folios_en_escritura"] = folios.astype("Int64")
        data["escritura_paquete"] = folios.gt(1).fillna(False).astype(bool)
        # Valor repetido: todos los folios del paquete llevan el mismo valor, que entonces
        # corresponde al total del negocio y no al precio individual de cada folio.
        valores_distintos = grupo["valor"].transform("nunique")
        data["valor_repetido_en_paquete"] = (
            data["escritura_paquete"] & valores_distintos.eq(1)
        ).fillna(False).astype(bool)
    if {"valor", "divipola", "fecha_escritura", "escritura_rezagada", "escritura_paquete"}.issubset(data.columns):
        # Valor simbólico: solo se busca entre compraventas individuales y contemporáneas.
        # Los valores bajos de escrituras rezagadas (precios de otra época) o de folios en
        # paquete (p. ej. un parqueadero) tienen explicación y no se marcan aquí.
        base = (
            data["valor"].gt(0)
            & ~data["escritura_rezagada"]
            & ~data["escritura_paquete"]
            & ~data.get("anotacion_duplicada", pd.Series(False, index=data.index)).fillna(False).astype(bool)
        )
        anio_escritura = data["fecha_escritura"].dt.year
        valores_base = data["valor"].where(base)
        por_celda = valores_base.groupby([data["divipola"], anio_escritura])
        mediana_celda = por_celda.transform("median")
        registros_celda = por_celda.transform("count")
        # Municipio-año con pocos registros: se usa la mediana del municipio en todo el periodo.
        mediana_municipio = valores_base.groupby(data["divipola"]).transform("median")
        mediana_ref = mediana_celda.where(registros_celda >= MIN_REGISTROS_CELDA, mediana_municipio)
        data["valor_relativo_mediana"] = data["valor"] / mediana_ref
        data["valor_simbolico"] = (
            base
            & (data["valor"].lt(UMBRAL_VALOR_ABSURDO)| data["valor_relativo_mediana"].lt(FRACCION_MEDIANA_SIMBOLICO))).fillna(False).astype(bool)
    if "matricula" in data:
        data["matricula_valida"] = data["matricula"].notna() & data["matricula"].ne("")
    if {"valor_valido", "registro_duplicado", "matricula_valida"}.issubset(data.columns):
        data["incluido_universo_modelado"] = (data["valor_valido"] & ~data["registro_duplicado"] & data["matricula_valida"])
        if "anotacion_duplicada" in data:
            data["incluido_universo_modelado"] &= ~data["anotacion_duplicada"]
        if "valor_simbolico" in data:
            data["incluido_universo_modelado"] &= ~data["valor_simbolico"]
    return data


BANDERAS_CALIDAD = (
    "valor_valido",
    "valor_simbolico_o_invalido",
    "valor_simbolico",
    "registro_duplicado",
    "anotacion_duplicada",
    "radicacion_antes_de_escritura",
    "escritura_rezagada",
    "escritura_paquete",
    "valor_repetido_en_paquete",
    "incluido_universo_modelado",
)


def profile_transactions(frame: pd.DataFrame) -> dict[str, Any]:
    """Summarize completeness, cardinality, duplicate keys and quality flags."""
    key = frame["pk"] if "pk" in frame else pd.Series(dtype="string")
    total = len(frame)
    banderas = {
        bandera: {
            "registros": int(frame[bandera].sum()),
            "pct": round(float(frame[bandera].mean()) * 100, 2) if total else 0.0,
        }
        for bandera in BANDERAS_CALIDAD
        if bandera in frame
    }
    return {
        "rows": int(total),
        "columns": int(len(frame.columns)),
        "missing_by_column": frame.isna().sum().astype(int).to_dict(),
        "duplicate_rows": int(frame.duplicated().sum()),
        "duplicate_pk": int(key.duplicated().sum()),
        "unique_departments": int(frame["departamento"].nunique()) if "departamento" in frame else 0,
        "unique_municipalities": int(frame["municipio"].nunique()) if "municipio" in frame else 0,
        "banderas_calidad": banderas,
    }
