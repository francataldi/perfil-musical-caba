"""
Contrato de datos al que convergen todas las fuentes de eventos.

Cada scraper de scripts/ produce un DataFrame con estas columnas y llama a
validar_esquema_evento() antes de escribir a disco. Definir el contrato una vez
y en un solo lugar es lo que evita que el scraper 3 devuelva algo incompatible
con el scraper 1 y que el problema aparezca recién en la Etapa 4.

Este módulo es importable y no tiene efectos secundarios: no toca la red ni el
disco. Todo eso vive en scripts/.
"""

import hashlib
from datetime import UTC, datetime

import pandas as pd

# El contrato. Cada entrada es (nombre_de_columna, dtype esperado en el parquet).
# El orden es el del protocolo (docs/00_protocolo.md) y se respeta al construir
# los DataFrames para que un `head()` de cualquier fuente se lea igual.
COLUMNAS_EVENTO = {
    "id": "string",  # hash determinístico, clave primaria
    "fuente": "string",  # de qué scraper vino
    "fecha": "datetime64[ns]",  # cuándo ocurre el evento
    "titulo": "string",
    "artistas": "object",  # list[str]; parquet lo guarda como lista anidada
    "venue_nombre": "string",
    "venue_direccion": "string",
    "venue_lat": "float64",  # nullable: se completa en la Etapa 2
    "venue_lon": "float64",
    "descripcion": "string",
    "url": "string",
    "scraped_at": "datetime64[ns]",  # cuándo se obtuvo el dato
}

# Columnas sin las cuales una fila no sirve para nada: sin fecha no hay trimestre,
# sin venue no hay barrio, sin id no hay deduplicación posible.
COLUMNAS_OBLIGATORIAS = ("id", "fuente", "fecha", "venue_nombre")


def generar_id_evento(fuente, identificador_en_la_fuente):
    """
    Genera el identificador único y estable de un evento.

    Objetivo
    --------
    Hacer que los scrapers sean IDEMPOTENTES: correrlos dos veces no puede
    duplicar filas. Un autoincremental no serviría, porque el mismo evento
    recibiría el id 1 en la primera corrida y el id 4.312 en la segunda, y no
    habría forma de reconocer que son el mismo. El hash, en cambio, depende solo
    del contenido: la misma entrada produce siempre la misma salida, hoy, mañana
    y en otra máquina.

    Se usa SHA-256 y no hash() de Python porque hash() sobre strings está
    aleatorizado por proceso (PYTHONHASHSEED): daría un valor distinto en cada
    ejecución, que es exactamente lo contrario de lo que se necesita acá.

    Se trunca a 16 caracteres hexadecimales (64 bits). Con ese espacio, la
    probabilidad de colisión para el orden de magnitud de este proyecto
    (~10^4 eventos) es despreciable, y el id sigue siendo legible al depurar.

    Inputs
    ------
    fuente : str
        Nombre del scraper de origen, p.ej. "ba_data_actividades".
    identificador_en_la_fuente : str
        Lo que identifica al evento DENTRO de esa fuente: el id nativo si lo
        tiene, o una combinación estable de campos si no lo tiene.

    Devuelve
    --------
    str de 16 caracteres hexadecimales.
    """
    clave_compuesta = f"{fuente}|{identificador_en_la_fuente}"
    return hashlib.sha256(clave_compuesta.encode("utf-8")).hexdigest()[:16]


def marca_de_tiempo_de_scraping():
    """
    Devuelve el instante actual en UTC, para la columna scraped_at.

    Objetivo
    --------
    Registrar CUÁNDO se obtuvo cada dato. Sin esto no se puede reconstruir qué
    mostraba la fuente en qué momento, y la reproducibilidad se pierde para
    siempre: si dentro de seis meses el sitio cambia y los números no dan, no
    hay manera de saber si el error es del análisis o de que la fuente se movió.

    Se usa UTC y no hora local para que dos corridas en máquinas con husos
    distintos sean comparables.

    Devuelve
    --------
    datetime naive en UTC (sin tzinfo), compatible con datetime64[ns] de parquet.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def dataframe_evento_vacio():
    """
    Devuelve un DataFrame vacío con el esquema completo y los dtypes correctos.

    Objetivo
    --------
    Darle a cada scraper un punto de partida canónico y evitar que el orden de
    las columnas dependa de en qué orden las fue creando. También sirve para que
    un scraper que no encuentra nada devuelva algo con la forma correcta en vez
    de None, y el código que lo consume no tenga que ramificar.

    Devuelve
    --------
    DataFrame de 0 filas con las columnas de COLUMNAS_EVENTO.
    """
    dataframe_vacio = pd.DataFrame(columns=list(COLUMNAS_EVENTO))
    for nombre_columna, tipo_esperado in COLUMNAS_EVENTO.items():
        dataframe_vacio[nombre_columna] = dataframe_vacio[nombre_columna].astype(
            tipo_esperado
        )
    return dataframe_vacio


def validar_esquema_evento(eventos, permitir_coordenadas_nulas=True):
    """
    Verifica que un DataFrame cumpla el contrato Evento antes de persistirlo.

    Objetivo
    --------
    Fallar en el punto de origen y no tres etapas después. Un scraper que
    devuelve una columna con otro nombre, o fechas como string, no rompe nada
    de inmediato: rompe en la Etapa 4 cuando se intenta agrupar por trimestre,
    y para entonces ya no se sabe cuál de los tres scrapers lo causó.

    Es la misma lógica que closure() rechazando ceros en src/composicional.py:
    los errores de pipeline se detienen donde se producen.

    Inputs
    ------
    eventos : DataFrame
        El resultado de un scraper, antes de escribir a parquet.
    permitir_coordenadas_nulas : bool, default True
        Si es True, venue_lat y venue_lon pueden venir vacías: se completan en
        la Etapa 2 (geocodificación). Se pasa False para validar el dataset ya
        geocodificado.

    Devuelve
    --------
    None. La función es un chequeo: o pasa en silencio, o levanta.

    Raises
    ------
    ValueError con el detalle de qué falló y en qué columna.
    """
    columnas_faltantes = set(COLUMNAS_EVENTO) - set(eventos.columns)
    if columnas_faltantes:
        raise ValueError(
            f"Faltan columnas del esquema Evento: {sorted(columnas_faltantes)}. "
            "Usá dataframe_evento_vacio() como punto de partida."
        )

    for nombre_columna in COLUMNAS_OBLIGATORIAS:
        cantidad_de_nulos = eventos[nombre_columna].isna().sum()
        if cantidad_de_nulos > 0:
            raise ValueError(
                f"La columna obligatoria '{nombre_columna}' tiene {cantidad_de_nulos} "
                "valores nulos. Sin ella la fila no sirve: no se puede asignar "
                "trimestre, barrio ni deduplicar."
            )

    if not pd.api.types.is_datetime64_any_dtype(eventos["fecha"]):
        raise ValueError(
            f"'fecha' tiene dtype {eventos['fecha'].dtype} en vez de datetime64. "
            "Convertila con pd.to_datetime() en el scraper, no después."
        )

    if not pd.api.types.is_datetime64_any_dtype(eventos["scraped_at"]):
        raise ValueError(
            f"'scraped_at' tiene dtype {eventos['scraped_at'].dtype} en vez de "
            "datetime64. Usá marca_de_tiempo_de_scraping()."
        )

    # El id es la clave de deduplicación: si se repite dentro de una misma fuente,
    # el identificador nativo elegido no distingue eventos y hay que revisarlo.
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
                raise ValueError(
                    f"'{nombre_columna}' tiene {cantidad_de_nulos} nulos y se pidió "
                    "validación con coordenadas obligatorias."
                )

    # Chequeo de rango: CABA está aproximadamente entre -34.71/-34.53 de latitud y
    # -58.53/-58.33 de longitud. Un punto muy afuera es casi siempre lat y lon
    # invertidas, que es el error de geocodificación más común y más silencioso.
    coordenadas_presentes = eventos.dropna(subset=["venue_lat", "venue_lon"])
    if len(coordenadas_presentes) > 0:
        latitudes_fuera_de_rango = (
            (coordenadas_presentes["venue_lat"] < -35.0)
            | (coordenadas_presentes["venue_lat"] > -34.0)
        ).sum()
        longitudes_fuera_de_rango = (
            (coordenadas_presentes["venue_lon"] < -59.0)
            | (coordenadas_presentes["venue_lon"] > -58.0)
        ).sum()
        if latitudes_fuera_de_rango or longitudes_fuera_de_rango:
            raise ValueError(
                f"Hay {latitudes_fuera_de_rango} latitudes y "
                f"{longitudes_fuera_de_rango} longitudes fuera del entorno de CABA. "
                "La causa más frecuente es lat y lon invertidas."
            )
