"""Parte I – ¿Qué actos jurídicos mencionan COMPRAVENTA en el Eje Cafetero?

El objetivo es verificar si el código 125 es el único acto de compraventa o si hay otros
que habría que incluir o excluir explícitamente. Solo hace conteos, no descarga filas.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.igac_inmobiliario.api import RESOURCE_URL, SocrataClient

cliente = SocrataClient()
where = (
    "departamento in ('CALDAS','RISARALDA','QUINDÍO') "
    "and year_radica between '2015' and '2023' "
    "and upper(nombre_natujur) like '%COMPRAVENTA%'"
)
respuesta = cliente.session.get(
    RESOURCE_URL,
    params={
        "$select": "cod_natujur, nombre_natujur, count(*) as registros",
        "$where": where,
        "$group": "cod_natujur, nombre_natujur",
        "$order": "count(*) DESC",
    },
    timeout=120,
)
respuesta.raise_for_status()
filas = respuesta.json()

total = sum(int(f["registros"]) for f in filas)
print(f"{'código':>7}  {'registros':>10}  {'%':>6}  acto")
for f in filas:
    n = int(f["registros"])
    print(f"{f['cod_natujur']:>7}  {n:>10,}  {n / total * 100:>5.1f}%  {f['nombre_natujur']}")
print(f"{'TOTAL':>7}  {total:>10,}")