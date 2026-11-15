"""Carga de las fuentes complementarias (IPC, IPVN y tasas de colocación) como series encadenadas."""
import numpy as np
import pandas as pd

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
         "Septiembre", "Octubre", "Noviembre", "Diciembre"]
AREAS_IPVN_EJE = {"Armenia AU": ["63001"], "Pereira AU": ["66001", "66170"], "Manizales AU": ["17001", "17873"]}


def cargar_ipc(ruta):
    """IPC nacional mensual encadenado desde las variaciones mensuales (dic-2002 = 100)."""
    x = pd.read_excel(ruta, header=None)
    fila_anios = x.index[x[0].astype(str).str.strip() == "Mes"][0]
    anios = x.loc[fila_anios, 1:].dropna()
    filas = []
    for i in range(fila_anios + 1, fila_anios + 13):
        mes = MESES.index(str(x.loc[i, 0]).strip()) + 1
        for col, anio in anios.items():
            v = pd.to_numeric(x.loc[i, col], errors="coerce")
            if pd.notna(v):
                filas.append({"anio": int(anio), "mes": mes, "var_mensual": float(v)})
    ipc = pd.DataFrame(filas).sort_values(["anio", "mes"]).reset_index(drop=True)
    ipc["ipc"] = 100 * (1 + ipc["var_mensual"] / 100).cumprod()
    return ipc


def cargar_ipvn(ruta):
    """IPVN trimestral encadenado por área (Anexo 4, variación trimestral), I-2004 = 100 * (1+var)."""
    x = pd.read_excel(ruta, sheet_name="ÁREAS TOTAL ", header=None)
    fila = x.index[x[0].astype(str).str.strip() == "Períodos"][0]
    columnas = {str(x.loc[fila, c]).strip(): c for c in range(2, 20)}
    filas, anio = [], None
    trim = {"I": 1, "II": 2, "III": 3, "IV": 4}
    for i in range(fila + 1, len(x)):
        if pd.notna(x.loc[i, 0]) and str(x.loc[i, 0]).strip().isdigit():
            anio = int(x.loc[i, 0])
        t = str(x.loc[i, 1]).strip()
        if t not in trim or anio is None:
            continue
        for area in AREAS_IPVN_EJE:
            v = pd.to_numeric(x.loc[i, columnas[area]], errors="coerce")
            filas.append({"area": area, "anio": anio, "trimestre": trim[t], "var_trim": v})
    ipvn = pd.DataFrame(filas).dropna(subset=["var_trim"]).sort_values(["area", "anio", "trimestre"])
    ipvn["ipvn"] = ipvn.groupby("area")["var_trim"].transform(lambda s: 100 * (1 + s / 100).cumprod())
    return ipvn.reset_index(drop=True)


def cargar_tasas(ruta):
    x = pd.read_excel(ruta, header=None).iloc[2:, [0, 1, 10, 11]]
    x.columns = ["fecha", "cuenta", "tasa", "monto"]
    x["fecha"] = pd.to_datetime(x["fecha"]).ffill()
    x["tipo"] = np.where(x["cuenta"].str.contains("diferente"), "tasa_no_vis", "tasa_vis")
    t = x.pivot_table(index="fecha", columns="tipo", values="tasa").reset_index()
    t["anio"], t["mes"] = t["fecha"].dt.year, t["fecha"].dt.month
    return t.sort_values("fecha").reset_index(drop=True)
