"""Parte II: diagnóstico de las causas de limpieza y aplicación de las decisiones.

Uso: python src/limpieza_parte2.py   (requiere data/base_banderas.parquet generado por src/banderas.py)
Salidas: salidas/parte2/resultados_parte2.json y data/base_limpia.parquet
"""
import json
import sys

sys.path.insert(0, "src")
import numpy as np
import pandas as pd

from fuentes import cargar_ipc

R = {}
d = pd.read_parquet("data/base_banderas.parquet")
for c in ["count_a", "count_de", "predios_nuevos", "tiene_valor", "tiene_mas_de_un_valor"]:
    d[c] = pd.to_numeric(d[c])
N = len(d)

# ---------------------------------------------------------------- fechas y pesos constantes
fr = d["fecha_radica_texto"]
d["fecha_radica"] = (pd.to_datetime(fr.str[:10], format="%Y-%m-%d", errors="coerce")
                     .fillna(pd.to_datetime(fr, format="%d/%m/%Y", errors="coerce"))
                     .fillna(pd.to_datetime(fr, format="%d/%m/%y", errors="coerce")))
assert d["fecha_radica"].notna().all()
lag = (d["fecha_radica"] - d["fecha_escritura"]).dt.days
normal = d["incluido_universo_modelado"] & d["rezago_escritura_anios"].between(0, 1) & lag.ge(0)
lag_orip = lag[normal].groupby(d.loc[normal, "orip"]).median()
R["rezago_dias_mediano"] = float(lag[normal].median())
R["rezago_dias_p90"] = float(lag[normal].quantile(0.9))

# Imputación de la fecha en "radicación anterior a la escritura": fecha de radicación menos el rezago mediano de su oficina
imp = d["radicacion_antes_de_escritura"]
d["fecha_imputada"] = imp
d["fecha_analisis"] = d["fecha_escritura"]
d.loc[imp, "fecha_analisis"] = d.loc[imp, "fecha_radica"] - pd.to_timedelta(d.loc[imp, "orip"].map(lag_orip).fillna(R["rezago_dias_mediano"]), unit="D")
d["anio_analisis"] = d["fecha_analisis"].dt.year
R["fecha_imputada"] = int(imp.sum())
R["fecha_imputada_formato_dd_mm_aa"] = float(d.loc[imp, "documento_justificativo"].str.contains(r"DEL \d{1,2}/\d{1,2}/\d{2}\b").mean())
R["fecha_imputada_orip100"] = int((imp & d["orip"].eq("100")).sum())
R["fecha_imputada_dias_mediana_desfase"] = float((d.loc[imp, "fecha_escritura"] - d.loc[imp, "fecha_radica"]).dt.days.median())

ipc = cargar_ipc("data/33337669-anex-IPC-Variacion-oct2026.xlsx")
ipc_2023 = ipc.loc[ipc["anio"] == 2023, "ipc"].mean()
clave_ipc = ipc.set_index(["anio", "mes"])["ipc"]
d["ipc"] = pd.MultiIndex.from_arrays([d["fecha_analisis"].dt.year, d["fecha_analisis"].dt.month]).map(clave_ipc)
d["valor_2023"] = d["valor"] * ipc_2023 / d["ipc"]
d["log_valor_2023"] = np.log(d["valor_2023"].where(d["valor"] > 0))

# ---------------------------------------------------------------- Parte II: diagnóstico
U = d["incluido_universo_modelado"]
diag = {}
diag["valor_nulo"] = int(d["valor"].isna().sum())
diag["valor_cero"] = int(d["valor"].eq(0).sum())
sin_valor = d["valor_simbolico_o_invalido"]
dos_orip = d["orip"].isin(["282", "106"])
diag["sin_valor_en_282_106"] = int((sin_valor & dos_orip).sum())
diag["pct_sin_valor_282_106_2015_2020"] = float(sin_valor[dos_orip & d["year_radica"].le(2020)].mean() * 100)
diag["pct_sin_valor_282_106_2021"] = float(sin_valor[dos_orip & d["year_radica"].eq(2021)].mean() * 100)
diag["pct_sin_valor_282_106_2022_2023"] = float(sin_valor[dos_orip & d["year_radica"].ge(2022)].mean() * 100)
diag["pct_sin_valor_resto"] = float(sin_valor[~dos_orip].mean() * 100)
diag["sin_valor_lote_sin_estado"] = float(sin_valor[d["estado_folio"].isna()].mean() * 100)
mun_sv = d.groupby("municipio")["valor_simbolico_o_invalido"].mean()
diag["municipios_mas_50_sin_valor"] = {k: round(v * 100, 1) for k, v in mun_sv[mun_sv > 0.5].sort_values(ascending=False).items()}
diag["registros_municipios_mas_50"] = int(d["municipio"].isin(mun_sv[mun_sv > 0.5].index).sum())
diag["count_a_0"] = int(d["count_a"].eq(0).sum())
diag["count_de_0"] = int(d["count_de"].eq(0).sum())
diag["count_a_0_orip100"] = int((d["count_a"].eq(0) & d["orip"].eq("100")).sum())
diag["tiene_mas_de_un_valor"] = int(d["tiene_mas_de_un_valor"].eq(1).sum())
diag["tiene_valor_con_cero"] = int((d["tiene_valor"].eq(1) & d["valor"].eq(0)).sum())
diag["doc_no_escritura"] = int((~d["documento_justificativo"].str.contains(r"^\d{2}-\s*ESCRITURA")).sum())
fa = pd.to_datetime(d["fecha_apertura_texto"].str[:10], format="%Y-%m-%d", errors="coerce")
diag["apertura_posterior_escritura"] = int((fa > d["fecha_escritura"]).sum())
diag["fecha_radica_formatos"] = d["fecha_radica_texto"].str.replace(r"\d", "9", regex=True).value_counts().to_dict()
diag["anio_escritura_min"] = int(d["anio_escritura"].min())
diag["escritura_antes_2015"] = int((d["anio_escritura"] < 2015).sum())

# Extremos: puntaje robusto del log-valor dentro de municipio-año-zona (mediana y MAD), solo universo modelado
u = d[U].copy()
g = u.groupby(["divipola", "anio_escritura", "tipo_predio_zona"])["log_valor_2023"]
med = g.transform("median")
mad = g.transform(lambda s: (s - s.median()).abs().median())
n_g = g.transform("size")
u["z_nivel"] = (0.6745 * (u["log_valor_2023"] - med) / mad).where(n_g >= 30)
d["z_nivel"] = u["z_nivel"]
d["extremo_alto"] = d["z_nivel"] > 3.5
d["extremo_bajo"] = d["z_nivel"] < -3.5
diag["extremo_alto_universo"] = int(d["extremo_alto"].sum())
diag["extremo_bajo_universo"] = int(d["extremo_bajo"].sum())
diag["extremo_alto_en_paquete"] = int((d["extremo_alto"] & d["escritura_paquete"]).sum())
diag["extremo_sin_grupo_30"] = int((U & d["z_nivel"].isna()).sum())
diag["valor_mayor_10mil_millones"] = int((U & d["valor"].gt(1e10)).sum())
diag["valor_mayor_10mil_millones_paquete"] = int((U & d["valor"].gt(1e10) & d["escritura_paquete"]).sum())
diag["valor_maximo"] = float(d.loc[U, "valor"].max())
C0 = d["candidato_indice"]
diag["extremo_alto_candidatos"] = int((d["extremo_alto"] & C0).sum())
diag["extremo_bajo_candidatos"] = int((d["extremo_bajo"] & C0).sum())

# Paquetes: ¿sirve prorratear el total entre los folios?
pq = d[d["escritura_paquete"] & U & ~d["valor_repetido_en_paquete"]]
gp = pq.groupby("clave_escritura")
total = gp["valor"].transform("sum")
nfol = gp["matricula"].transform("nunique")
err = np.log(pq["valor"] / (total / nfol))
diag["prorrateo_paquetes_prueba"] = int(pq["clave_escritura"].nunique())
diag["prorrateo_folios_prueba"] = int(len(pq))
diag["prorrateo_error_mediano_pct"] = float((np.exp(np.median(np.abs(err))) - 1) * 100)
diag["prorrateo_dentro_20pct"] = float((np.abs(err) < np.log(1.2)).mean() * 100)
diag["cuota_folio_mayor_mediana"] = float((gp["valor"].max() / gp["valor"].sum()).median() * 100)
rp = d[d["valor_repetido_en_paquete"] & U]
diag["repetido_dos_folios_pct"] = float(rp["folios_en_escritura"].eq(2).mean() * 100)
diag["repetido_mediana_mill"] = float(rp["valor"].median() / 1e6)
diag["individual_mediana_mill"] = float(d.loc[C0, "valor"].median() / 1e6)

# Rezagadas: ¿la inflación explica su valor bajo?
z = d[d["escritura_rezagada"] & d["valor_valido"] & ~d["anotacion_duplicada"] & d["ipc"].notna()]
diag["rezagadas_con_ipc"] = int(len(z))
diag["rezagadas_mediana_2023"] = {f"{a}-{b}": float(z.loc[z["rezago_escritura_anios"].between(a, b), "valor_2023"].median() / 1e6)
                                  for a, b in [(2, 2), (3, 5), (6, 10), (11, 200)]}
diag["candidatos_mediana_2023"] = float(d.loc[C0, "valor_2023"].median() / 1e6)
R["diagnostico"] = diag

# ---------------------------------------------------------------- Parte II: base para el índice
d["base_indice"] = C0 & d["tiene_mas_de_un_valor"].eq(0)
embudo = [("Universo de análisis (código 125)", N),
          ("Universo modelado (valor válido, sin duplicados ni valor simbólico)", int(U.sum())),
          ("Sin valor total repetido en paquete", int((U & ~d["valor_repetido_en_paquete"]).sum())),
          ("Sin escrituras rezagadas", int(C0.sum())),
          ("Sin anotaciones con más de un valor", int(d["base_indice"].sum()))]
R["embudo_limpieza"] = embudo
R["base_indice_con_fecha_imputada"] = int((d["base_indice"] & d["fecha_imputada"]).sum())

import os

os.makedirs("salidas/parte2", exist_ok=True)
d.to_parquet("data/base_limpia.parquet", index=False)
json.dump(R, open("salidas/parte2/resultados_parte2.json", "w"), ensure_ascii=False, indent=1, default=str)
for paso, n in R["embudo_limpieza"]:
    print(f"{paso:75s} {n:>9,}")
