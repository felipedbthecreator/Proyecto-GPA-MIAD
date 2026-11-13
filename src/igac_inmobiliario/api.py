"""Socrata client with bounded and complete paginated queries."""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DATASET_ID = os.getenv("SOCRATA_DATASET_ID", "7y2j-43cv")
DOMAIN = os.getenv("SOCRATA_DOMAIN", "www.datos.gov.co")
RESOURCE_URL = f"https://{DOMAIN}/resource/{DATASET_ID}.json"
METADATA_URL = f"https://{DOMAIN}/api/views/{DATASET_ID}"
# Socrata no garantiza el orden de las filas sin $order; paginar sin ordenar
# puede repetir o saltar registros. ":id" es el id interno de fila (único y estable).
STABLE_ORDER = ":id"

# Errores de red ante los que vale la pena volver a pedir la misma página.
ERRORES_RED = (
    requests.exceptions.ChunkedEncodingError,  # conexión cortada a mitad de la respuesta
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)


class SocrataClient:
    """Fetch metadata or bounded data from a Socrata dataset."""

    def __init__(self, timeout: int = 120, intentos_pagina: int = 6) -> None:
        self.timeout = timeout
        self.intentos_pagina = intentos_pagina
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        reintentos = Retry(total=5,backoff_factor=2,status_forcelist=(429, 500, 502, 503, 504),allowed_methods=("GET",),)
        self.session.mount("https://", HTTPAdapter(max_retries=reintentos))

    def _get_page(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Pide una página y la reintenta si la conexión se cae, sin perder lo ya descargado."""
        for intento in range(1, self.intentos_pagina + 1):
            try:
                response = self.session.get(RESOURCE_URL, params=params, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            except ERRORES_RED as error:
                if intento == self.intentos_pagina:
                    raise
                espera = 5 * 2 ** (intento - 1)  # 5, 10, 20, 40, 80 segundos
                print(
                    f"  Falla de conexión en offset {params.get('$offset', 0):,} "
                    f"({type(error).__name__}). Reintento {intento}/{self.intentos_pagina - 1} "
                    f"en {espera} s..."
                )
                time.sleep(espera)
        return []

    def metadata(self) -> dict[str, Any]:
        response = self.session.get(METADATA_URL, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def count(self, *, where: Optional[str] = None) -> int:
        """Return the number of rows matching a SoQL predicate."""
        params: dict[str, Any] = {"$select": "count(*) as registros"}
        if where:
            params["$where"] = where
        response = self.session.get(RESOURCE_URL, params=params, timeout=self.timeout)
        response.raise_for_status()
        result = response.json()
        if not result or "registros" not in result[0]:
            raise ValueError("Socrata returned no count for the requested predicate")
        return int(result[0]["registros"])

    def fetch(
        self,
        *,
        limit: int = 5_000,
        page_size: int = 1_000,
        where: Optional[str] = None,
        select: str = "*",
        order: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch at most ``limit`` rows using Socrata's offset pagination."""
        if limit < 1 or page_size < 1:
            raise ValueError("limit and page_size must be positive")
        rows: list[dict[str, Any]] = []
        for offset in range(0, limit, page_size):
            params: dict[str, Any] = {
                "$select": select,
                "$limit": min(page_size, limit - offset),
                "$offset": offset,
            }
            if where:
                params["$where"] = where
            params["$order"] = order or STABLE_ORDER
            page = self._get_page(params)
            if not page:
                break
            rows.extend(page)
            if len(page) < params["$limit"]:
                break
        return pd.DataFrame(rows)

    def fetch_all(
        self,
        *,
        where: Optional[str] = None,
        select: str = "*",
        page_size: int = 5_000,
        expected_rows: Optional[int] = None,
    ) -> pd.DataFrame:
        """Fetch all matching rows, stopping only at the API result boundary."""
        if page_size < 1:
            raise ValueError("page_size must be positive")
        total = expected_rows if expected_rows is not None else self.count(where=where)
        if total < 0:
            raise ValueError("expected_rows must not be negative")
        rows: list[dict[str, Any]] = []
        for offset in range(0, total, page_size):
            params: dict[str, Any] = {
                "$select": select,
                "$limit": page_size,
                "$offset": offset,
                "$order": STABLE_ORDER,
            }
            if where:
                params["$where"] = where
            page = self._get_page(params)
            if not page:
                break
            rows.extend(page)
            print(f"Descargadas {len(rows):,}/{total:,} filas")
            if len(page) < page_size:
                break

        if len(rows) != total:
            print(f"ADVERTENCIA: se descargaron {len(rows):,} filas y se esperaban {total:,}.")
        return pd.DataFrame(rows)