"""Reconstrucción de las banderas de calidad (Parte I) a partir del CSV crudo del IGAC.

Uso: python -I src/banderas.py data/compraventas_eje_cafetero_completo_crudo.csv data/base_banderas.parquet
"""
import re
import sys

import numpy as np
import pandas as pd

RE_FECHA = re.compile(r"\bDEL?\s+(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
RE_NUMERO = re.compile(r"ESCRITURA\s+(\d+)")


def fecha_escritura(doc: pd.Series) -> pd.Series:
    partes = doc.str.extract(RE_FECHA)
    dia, mes, anio = (pd.to_numeric(partes[i], errors="coerce") for i in range(3))
    anio = np.where(anio < 100, np.where(anio <= 30, 2000 + anio, 1900 + anio), anio)
    return pd.to_datetime(pd.DataFrame({"year": anio, "month": mes, "day": dia}), errors="coerce")


def construir(ruta_csv: str) -> pd.DataFrame:
    d = pd.read_csv(ruta_csv, dtype=str)
    d["valor"] = pd.to_numeric(d["valor"])
    d["year_radica"] = pd.to_numeric(d["year_radica"]).astype(int)
    d["num_anotacion"] = pd.to_numeric(d["num_anotacion"]).astype(int)
    d["divipola"] = d["divipola"].str.zfill(5)
    d["fecha_escritura"] = fecha_escritura(d["documento_justificativo"])
    d["anio_escritura"] = d["fecha_escritura"].dt.year

    # Valor
    d["valor_valido"] = d["valor"].gt(0)
    d["valor_simbolico_o_invalido"] = ~d["valor_valido"]

    # Coherencia temporal
    d["rezago_escritura_anios"] = d["year_radica"] - d["anio_escritura"]
    d["radicacion_antes_de_escritura"] = d["rezago_escritura_anios"] < 0
    d["escritura_rezagada"] = d["rezago_escritura_anios"] >= 2

    # Matrícula: prefijo numérico de oficina + número de folio
    d["matricula_valida"] = d["matricula"].str.match(r"^[0-9A-Z]{3}-\d+$")

    # Duplicados: misma matrícula y número de anotación cargada en dos años.
    # Se conserva la copia cuyo año de radicación es el más cercano (y no anterior) al de la escritura.
    d["_dist"] = np.where(d["rezago_escritura_anios"] >= 0, d["rezago_escritura_anios"], 100 - d["rezago_escritura_anios"])
    orden = d.sort_values(["matricula", "num_anotacion", "_dist", "year_radica"])
    d["anotacion_duplicada"] = orden.duplicated(["matricula", "num_anotacion"], keep="first").reindex(d.index)
    columnas_fuente = [c for c in d.columns if c not in ("pk",) and not c.startswith("_")][:23]
    d["registro_duplicado"] = d.duplicated(subset=[c for c in pd.read_csv(ruta_csv, nrows=0).columns if c != "pk"], keep="first")
    d = d.drop(columns="_dist")

    # Escrituras paquete: oficina + número de escritura + fecha de la escritura
    numero = pd.to_numeric(d["documento_justificativo"].str.extract(RE_NUMERO)[0], errors="coerce")
    d["clave_escritura"] = (d["orip"] + "|" + numero.astype("Int64").astype(str) + "|"
                            + d["fecha_escritura"].dt.strftime("%Y-%m-%d")).where(numero.notna())
    base_folios = d
    folios = base_folios.groupby("clave_escritura")["matricula"].nunique()
    d["folios_en_escritura"] = d["clave_escritura"].map(folios)
    d["escritura_paquete"] = d["folios_en_escritura"].gt(1)
    # Un solo valor informado (incluido el cero) para todos los folios del paquete
    con_valor = base_folios[base_folios["valor"].notna() & base_folios["escritura_paquete"]]
    repetido = con_valor.groupby("clave_escritura")["valor"].nunique() == 1
    d["valor_repetido_en_paquete"] = d["escritura_paquete"] & d["clave_escritura"].map(repetido).fillna(False).astype(bool)

    # Valor simbólico: <= 100.000 pesos o < 1% de la mediana municipio-año, solo en compraventas individuales y contemporáneas
    individual = d["valor_valido"] & ~d["valor_repetido_en_paquete"] & ~d["escritura_rezagada"] & ~d["anotacion_duplicada"]
    mediana = d[individual].groupby(["divipola", "anio_escritura"])["valor"].median()
    d["mediana_municipio_anio"] = pd.MultiIndex.from_frame(d[["divipola", "anio_escritura"]]).map(mediana)
    d["valor_relativo_mediana"] = d["valor"] / d["mediana_municipio_anio"]
    d["valor_simbolico"] = individual & ((d["valor"] <= 100_000) | (d["valor_relativo_mediana"] < 0.01))

    d["incluido_universo_modelado"] = (d["valor_valido"] & ~d["anotacion_duplicada"] & ~d["registro_duplicado"]
                                       & d["matricula_valida"] & ~d["valor_simbolico"])
    d["candidato_indice"] = d["incluido_universo_modelado"] & ~d["valor_repetido_en_paquete"] & ~d["escritura_rezagada"]
    return d


if __name__ == "__main__":
    base = construir(sys.argv[1])
    base.to_parquet(sys.argv[2], index=False)
    objetivos = {"valor_simbolico_o_invalido": 16047, "valor_simbolico": 616, "anotacion_duplicada": 3254,
                 "radicacion_antes_de_escritura": 4058, "escritura_rezagada": 2835, "escritura_paquete": 163916,
                 "valor_repetido_en_paquete": 97105, "incluido_universo_modelado": 437648, "candidato_indice": 338941}
    for k, v in objetivos.items():
        print(f"{k:32s} {int(base[k].sum()):>8,}  objetivo {v:>8,}  dif {int(base[k].sum()) - v:+,}")
    print("registro_duplicado", int(base["registro_duplicado"].sum()), "| matricula_valida", int(base["matricula_valida"].sum()),
          "| fecha nula", int(base["fecha_escritura"].isna().sum()), "| clave nula", int(base["clave_escritura"].isna().sum()))
