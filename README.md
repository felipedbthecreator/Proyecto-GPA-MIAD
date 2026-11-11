# Dinámica inmobiliaria en Colombia

Primer pipeline reproducible para consultar, limpiar y explorar el conjunto
**Registro de transacciones inmobiliarias en Colombia IGAC 2015–2023**,
publicado en datos.gov.co mediante Socrata (dataset `7y2j-43cv`).

## Alcance documentado (Entregas 2 y 3)

En esta primera versión se concentra en **compraventas** de **Caldas, Risaralda y Quindío**
entre **2015 y 2023**, como línea base del mercado previo al evento definido
en las entregas. El acto jurídico se filtra con `COD_NATUJUR = 125`
(`COMPRAVENTA`). La transferencia posterior a Medellín, Bogotá, Cali y
Barranquilla queda fuera de esta primera extracción y está condicionada a la
calidad y cobertura.

- Consulta de metadatos y datos mediante la API Socrata según los parametros definidos en nuestras entregas anteriores.
- Perfilado de tipos, faltantes, duplicados, valores inválidos y valores simbólicos.
- Normalización de fechas, campos numéricos, texto y códigos territoriales.
- Análisis preliminar de variables con estadísticas descriptivas, histogramas y
  correlaciones numéricas.
- Visualización exploratoria con tablas de contingencia, tablas resumen,
  histogramas, series temporales, barras agrupadas, diagramas de caja y
  dispersión. Los valores monetarios se muestran también en escala logarítmica
  por su asimetría; las cajas permiten revisar medianas, rango intercuartílico
  y posibles atípicos.
- Agregaciones exploratorias por año, departamento y municipio.
- Exportación de resultados reproducibles a `data/processed/`.

El caso del proyecto busca estudiar la dinámica inmobiliaria, el valor de las
transacciones y comportamientos atípicos. Esta entrega prepara la base
analítica; no interpreta un registro administrativo como prueba de una
transacción ilícita.

## Instalación

```bash
/usr/bin/python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Ejecución

El notebook es [01_limpieza_exploracion_transacciones_inmobiliarias.ipynb](notebooks/01_limpieza_exploracion_transacciones_inmobiliarias.ipynb).
También puede ejecutarse el pipeline base desde la raíz:

```bash
python -m src.igac_inmobiliario.pipeline --full --page-size 5000
```

El modo completo cuenta primero el universo y descarga todas las compraventas
del alcance (aproximadamente 457.558 filas) por páginas. El archivo completo
se guarda en `repositorio/data/processed/compraventas_eje_cafetero_completo_limpio.csv`.
Durante la exploración rápida se puede usar:

```bash
python -m src.igac_inmobiliario.pipeline --sample-size 2000 --page-size 1000
```

Las variables de configuración se pueden ajustar sin modificar el código:

```bash
SOCRATA_DOMAIN=www.datos.gov.co
SOCRATA_DATASET_ID=7y2j-43cv
```

Para el procesamiento completo, se debe revisar el costo de red y memoria:

```bash
python -m src.igac_inmobiliario.pipeline --full --page-size 5000
```

## Fuente y decisiones de calidad

- API de datos: <https://www.datos.gov.co/resource/7y2j-43cv.json>
- Metadatos: <https://www.datos.gov.co/api/views/7y2j-43cv>
- La clave `pk` se conserva y se verifica como identificador esperado.
- `MATRICULA` se conserva para evaluar si es posible reconocer ventas repetidas.
- El universo modelado exige `TIENE_VALOR = 1`, `VALOR > 0`, matrícula válida y
  ausencia de `pk` duplicado en el extracto; cada exclusión debe documentarse.
- Un valor faltante, no válido o simbólico no se imputa automáticamente.
- `COD_NATUJUR = 125` es la regla de inclusión de compraventas verificada en
  la API; otros actos como desenglobe y división no forman parte del universo
  modelado inicial.
- `fecha_radica_texto` y `fecha_apertura_texto` se convierten con coerción
  explícita; fechas imposibles quedan como faltantes y se reportan.
- Los campos numéricos se convierten con coerción explícita y no se imputan
  silenciosamente.
- `divipola` se conserva como texto de cuatro dígitos para no perder ceros.
- Las salidas derivadas no sustituyen los datos fuente y se excluyen del
  control de versiones.
