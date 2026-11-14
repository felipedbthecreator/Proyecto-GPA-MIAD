"""Fuentes complementarias: IPC (DANE), IPVN (DANE) y tasas de colocación de vivienda (BanRep).

Lee los anexos en Excel que publica el DANE y los convierte en tablas limpias,
listas para cruzar con la base del IGAC por año (y DIVIPOLA en el caso del IPVN).

Archivos esperados en data/raw/fuentes/ (no se suben a GitHub):
- anex-IPC-Variacion-oct2026.xlsx  -> variaciones mensuales del IPC nacional, 2003-2026
- anex-IPVN-IVtrim2023.xls          -> variaciones trimestrales del IPVN por área, 2004-2023
- tasas_colocacion_vivienda_2015_2023.xlsx -> tasas de colocación de adquisición de vivienda
  VIS y no VIS en pesos, mensual 2015-2023 (Banco de la República, SUAMECA)

Las dos series se publican como variaciones porcentuales; aquí se encadenan para
obtener índices. Como se trabaja con variaciones, no hace falta empalmar bases.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

MESES = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)

# Áreas del IPVN que cubren el Eje Cafetero y los municipios (DIVIPOLA) que agrupan,
# según la ficha del DANE: Pereira AU = Pereira + Dosquebradas;
# Manizales AU = Manizales + Villamaría; Armenia AU = Armenia.
AREAS_IPVN_EJE = {
    "Armenia AU": ("63001",),
    "Pereira AU": ("66001", "66170"),
    "Manizales AU": ("17001", "17873"),
}
TRIMESTRES = {"I": 1, "II": 2, "III": 3, "IV": 4}


def cargar_ipc(ruta: str | Path) -> pd.DataFrame:
    """IPC nacional mensual (base diciembre 2018 = 100) a partir del anexo de variaciones.

    Devuelve columnas: anio, mes, variacion_mensual, ipc.
    """
    hoja = pd.read_excel(ruta, sheet_name="VarNal", header=None)
    fila_encabezado = hoja.index[hoja.iloc[:, 0].astype(str).str.strip().eq("Mes")][0]
    anios = pd.to_numeric(hoja.iloc[fila_encabezado, 1:], errors="coerce")
    tabla = hoja.iloc[fila_encabezado + 1 : fila_encabezado + 13, :].copy()
    tabla.index = tabla.iloc[:, 0].astype(str).str.strip()
    if list(tabla.index) != list(MESES):
        raise ValueError("El anexo del IPC no tiene los 12 meses en el orden esperado")
    tabla = tabla.iloc[:, 1:].apply(pd.to_numeric, errors="coerce")
    tabla.columns = anios.astype("Int64")
    tabla = tabla.loc[:, tabla.columns.notna()]

    ipc = (
        tabla.reset_index(drop=True)
        .assign(mes=range(1, 13))
        .melt(id_vars="mes", var_name="anio", value_name="variacion_mensual")
        .dropna(subset=["variacion_mensual"])
        .astype({"anio": int})
        .sort_values(["anio", "mes"])
        .reset_index(drop=True)
    )
    ipc["ipc"] = (1 + ipc["variacion_mensual"] / 100).cumprod()
    base = ipc.loc[(ipc["anio"] == 2018) & (ipc["mes"] == 12), "ipc"].iloc[0]
    ipc["ipc"] = ipc["ipc"] / base * 100
    return ipc[["anio", "mes", "variacion_mensual", "ipc"]]


def ipc_promedio_anual(ipc: pd.DataFrame) -> pd.Series:
    """Promedio anual del IPC (para deflactar valores fechados por año)."""
    return ipc.groupby("anio")["ipc"].mean().rename("ipc_promedio")


def _bloque_ipvn(hoja: pd.DataFrame, titulo: str) -> pd.DataFrame:
    """Extrae de la hoja 'ÁREAS TOTAL' el bloque cuyo título contiene `titulo`."""
    columna = next(
        c for c in hoja.columns
        if hoja.iloc[2:6, c].astype(str).str.contains(titulo, case=False).any()
    )
    fila_encabezado = hoja.index[hoja.iloc[:, columna].astype(str).str.strip().eq("Períodos")][0]
    nombres = hoja.iloc[fila_encabezado, columna + 2 :].tolist()
    fin = nombres.index(next(n for n in nombres if pd.isna(n))) if any(pd.isna(n) for n in nombres) else len(nombres)
    areas = [str(n).strip() for n in nombres[:fin]]
    cuerpo = hoja.iloc[fila_encabezado + 1 :, columna : columna + 2 + fin].copy()
    cuerpo.columns = ["anio", "trimestre", *areas]
    cuerpo = cuerpo[cuerpo["trimestre"].astype(str).str.strip().isin(TRIMESTRES)].copy()
    cuerpo["anio"] = pd.to_numeric(cuerpo["anio"], errors="coerce").ffill().astype(int)
    cuerpo["trimestre"] = cuerpo["trimestre"].astype(str).str.strip().map(TRIMESTRES)
    largo = cuerpo.melt(id_vars=["anio", "trimestre"], var_name="area", value_name="variacion")
    largo["variacion"] = pd.to_numeric(largo["variacion"], errors="coerce")  # "(-)" -> vacío
    return largo


def cargar_ipvn(ruta: str | Path, areas: tuple[str, ...] | None = None) -> pd.DataFrame:
    """IPVN trimestral por área urbana, encadenado a partir de las variaciones trimestrales.

    Base: promedio de 2015 = 100 en cada área (inicio del periodo de la base del IGAC).
    Solo sirve para comparar tendencias entre áreas, no niveles de precio.
    Devuelve columnas: area, anio, trimestre, variacion_trimestral, ipvn,
    variacion_anual_publicada (para control).
    """
    hoja = pd.read_excel(ruta, sheet_name="ÁREAS TOTAL ", header=None)
    trimestral = _bloque_ipvn(hoja, "Variación trimestral")
    anual = _bloque_ipvn(hoja, "Variación anual").rename(columns={"variacion": "variacion_anual_publicada"})
    areas = areas or (*AREAS_IPVN_EJE, "Total")
    ipvn = (
        trimestral[trimestral["area"].isin(areas)]
        .rename(columns={"variacion": "variacion_trimestral"})
        .merge(anual, on=["area", "anio", "trimestre"], how="left")
        .sort_values(["area", "anio", "trimestre"])
        .reset_index(drop=True)
    )
    # Encadenar solo desde el primer dato disponible de cada área.
    con_dato = ipvn["variacion_trimestral"].notna()
    ipvn["ipvn"] = (
        (1 + ipvn["variacion_trimestral"].where(con_dato) / 100)
        .groupby(ipvn["area"]).cumprod()
    )
    base_2015 = ipvn[ipvn["anio"] == 2015].groupby("area")["ipvn"].mean()
    ipvn["ipvn"] = ipvn["ipvn"] / ipvn["area"].map(base_2015) * 100
    return ipvn


def ipvn_por_municipio_anio(ipvn: pd.DataFrame) -> pd.DataFrame:
    """IPVN promedio anual de cada área, repetido para cada DIVIPOLA que agrupa.

    Llave de cruce con la base del IGAC: divipola + anio.
    """
    anual = ipvn.groupby(["area", "anio"])["ipvn"].mean().rename("ipvn_promedio").reset_index()
    filas = [
        {"divipola": divipola, "area_ipvn": area}
        for area, divipolas in AREAS_IPVN_EJE.items()
        for divipola in divipolas
    ]
    return pd.DataFrame(filas).merge(anual, left_on="area_ipvn", right_on="area").drop(columns="area")


SERIES_TASAS = {
    "Adquisición de Vivienda VIS (Colocación en Pesos)": "tasa_vis",
    "Adquisición de Vivienda diferente de VIS (Colocación en Pesos)": "tasa_no_vis",
}


def cargar_tasas_vivienda(ruta: str | Path) -> pd.DataFrame:
    """Tasas de colocación mensuales para adquisición de vivienda (total establecimientos).

    El reporte de SUAMECA escribe la fecha solo en la primera fila de cada mes;
    se completa hacia abajo. Devuelve columnas: anio, mes, tasa_vis, tasa_no_vis
    (en % efectivo anual) y los montos desembolsados (miles de millones de pesos).
    """
    hoja = pd.read_excel(ruta, header=None)
    fila_encabezado = hoja.index[hoja.iloc[:, 0].astype(str).str.startswith("Fecha")][0]
    grupos = hoja.iloc[fila_encabezado - 1].ffill()
    col_total = [i for i, g in enumerate(grupos) if str(g).strip() == "Total establecimientos"]
    if len(col_total) != 2:
        raise ValueError("No se encontraron las columnas de 'Total establecimientos'")
    datos = hoja.iloc[fila_encabezado + 1 :, [0, 1, *col_total]].copy()
    datos.columns = ["fecha", "serie", "tasa", "monto"]
    datos["fecha"] = pd.to_datetime(datos["fecha"], errors="coerce").ffill()
    datos = datos[datos["serie"].isin(SERIES_TASAS)].copy()
    datos["serie"] = datos["serie"].map(SERIES_TASAS)
    datos[["tasa", "monto"]] = datos[["tasa", "monto"]].apply(pd.to_numeric, errors="coerce")
    tasas = datos.pivot_table(index="fecha", columns="serie", values=["tasa", "monto"])
    tasas.columns = [c if m == "tasa" else c.replace("tasa", "monto") for m, c in tasas.columns]
    tasas = tasas.reset_index().sort_values("fecha")
    tasas.insert(0, "anio", tasas["fecha"].dt.year)
    tasas.insert(1, "mes", tasas["fecha"].dt.month)
    return tasas.drop(columns="fecha").reset_index(drop=True)
