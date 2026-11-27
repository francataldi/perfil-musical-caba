import hashlib
from datetime import UTC, datetime

import pandas as pd

COLUMNAS_EVENTO = {
    "id": "string",
    "fuente": "string",
    "fecha": "datetime64[ns]",
    "titulo": "string",
    "artistas": "object",
    "venue_nombre": "string",
    "venue_direccion": "string",
    "venue_lat": "float64",
    "venue_lon": "float64",
    "descripcion": "string",
    "url": "string",
    "scraped_at": "datetime64[ns]",
}

COLUMNAS_OBLIGATORIAS = ("id", "fuente", "fecha", "venue_nombre")


def generar_id_evento(fuente, identificador_en_la_fuente):
    clave_compuesta = f"{fuente}|{identificador_en_la_fuente}"
    return hashlib.sha256(clave_compuesta.encode("utf-8")).hexdigest()[:16]


def marca_de_tiempo_de_scraping():
    return datetime.now(UTC).replace(tzinfo=None)


def dataframe_evento_vacio():
    dataframe_vacio = pd.DataFrame(columns=list(COLUMNAS_EVENTO))
    for nombre_columna, tipo_esperado in COLUMNAS_EVENTO.items():
        dataframe_vacio[nombre_columna] = dataframe_vacio[nombre_columna].astype(tipo_esperado)
    return dataframe_vacio


def validar_esquema_evento(eventos, permitir_coordenadas_nulas=True):
    columnas_faltantes = set(COLUMNAS_EVENTO) - set(eventos.columns)
    if columnas_faltantes:
        raise ValueError(f"Faltan columnas del esquema Evento: {sorted(columnas_faltantes)}. Usá dataframe_evento_vacio() como punto de partida.")

    for nombre_columna in COLUMNAS_OBLIGATORIAS:
        cantidad_de_nulos = eventos[nombre_columna].isna().sum()
        if cantidad_de_nulos > 0:
            raise ValueError(
                f"La columna obligatoria '{nombre_columna}' tiene {cantidad_de_nulos} "
                "valores nulos. Sin ella la fila no sirve: no se puede asignar "
                "trimestre, barrio ni deduplicar."
            )

    if not pd.api.types.is_datetime64_any_dtype(eventos["fecha"]):
        raise ValueError(f"'fecha' tiene dtype {eventos['fecha'].dtype} en vez de datetime64. Convertila con pd.to_datetime() en el scraper, no después.")

    if not pd.api.types.is_datetime64_any_dtype(eventos["scraped_at"]):
        raise ValueError(f"'scraped_at' tiene dtype {eventos['scraped_at'].dtype} en vez de datetime64. Usá marca_de_tiempo_de_scraping().")

    cantidad_de_ids_duplicados = eventos["id"].duplicated().sum()
    if cantidad_de_ids_duplicados > 0:
        raise ValueError(
            f"Hay {cantidad_de_ids_duplicados} ids duplicados. El identificador "
            "usado para el hash no distingue eventos distintos: revisá qué campos "
            "le estás pasando a generar_id_evento()."
        )

    if not permitir_coordenadas_nulas:
        for nombre_columna in ("venue_lat", "venue_lon"):
            cantidad_de_nulos = eventos[nombre_columna].isna().sum()
            if cantidad_de_nulos > 0:
                raise ValueError(f"'{nombre_columna}' tiene {cantidad_de_nulos} nulos y se pidió validación con coordenadas obligatorias.")

    coordenadas_presentes = eventos.dropna(subset=["venue_lat", "venue_lon"])
    if len(coordenadas_presentes) > 0:
        latitudes_fuera_de_rango = ((coordenadas_presentes["venue_lat"] < -35.0) | (coordenadas_presentes["venue_lat"] > -34.0)).sum()
        longitudes_fuera_de_rango = ((coordenadas_presentes["venue_lon"] < -59.0) | (coordenadas_presentes["venue_lon"] > -58.0)).sum()
        if latitudes_fuera_de_rango or longitudes_fuera_de_rango:
            raise ValueError(
                f"Hay {latitudes_fuera_de_rango} latitudes y "
                f"{longitudes_fuera_de_rango} longitudes fuera del entorno de CABA. "
                "La causa más frecuente es lat y lon invertidas."
            )
