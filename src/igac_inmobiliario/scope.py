"""Documented analytical scope from Entregas 2 y 3."""

from __future__ import annotations

from typing import Final

TARGET_DEPARTMENTS: Final[tuple[str, ...]] = ("CALDAS", "RISARALDA", "QUINDÍO")
START_YEAR: Final[int] = 2015
END_YEAR: Final[int] = 2023
COMPRAVENTA_CODE: Final[int] = 125

ANALYSIS_COLUMNS: Final[str] = ",".join(
    (
        "pk",
        "matricula",
        "fecha_radica_texto",
        "fecha_apertura_texto",
        "year_radica",
        "orip",
        "divipola",
        "departamento",
        "municipio",
        "tipo_predio_zona",
        "categoria_ruralidad_2024",
        "num_anotacion",
        "estado_folio",
        "folios_derivados",
        "dinamica_2024",
        "cod_natujur",
        "nombre_natujur",
        "documento_justificativo",
        "count_a",
        "count_de",
        "predios_nuevos",
        "tiene_valor",
        "tiene_mas_de_un_valor",
        "valor",
    )
)


def build_scope_where() -> str:
    """Build the SoQL predicate for the MVP universe."""
    departments = ",".join(f"'{department}'" for department in TARGET_DEPARTMENTS)
    return (
        f"departamento in ({departments}) "
        f"and year_radica between '{START_YEAR}' and '{END_YEAR}' "
        f"and cod_natujur = '{COMPRAVENTA_CODE}'"
    )
