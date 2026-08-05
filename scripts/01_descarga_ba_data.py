"""
Descarga eventos musicales del portal de datos abiertos del GCBA (BA Data).

Fuente: data.buenosaires.gob.ar, portal CKAN. Sin key, sin login.
Detalle en docs/01_fuentes.md.

ESTE ES UN SCRIPT, NO UNA LIBRERÍA. Toca la red y escribe a disco, así que todo
el efecto secundario vive dentro de main() y main() se llama solo desde el
bloque if __name__ == "__main__". Importarlo no puede disparar nada.

Uso:
    conda activate musica-caba
    python scripts/01_descarga_ba_data.py
"""

import sys
import time
from pathlib import Path

import pandas as pd
import requests

# Permite importar src/ cuando el script se corre desde la raíz del repo.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.esquema import (  # noqa: E402
    dataframe_evento_vacio,
    generar_id_evento,
    marca_de_tiempo_de_scraping,
    validar_esquema_evento,
)

URL_BASE_API_CKAN = "https://data.buenosaires.gob.ar/api/3/action"
SLUG_DATASET = "actividades-culturales"
NOMBRE_DE_LA_FUENTE = "ba_data_actividades"

# User-Agent honesto: si algo molesta, que puedan escribir en vez de bloquear.
CABECERAS_HTTP = {
    "User-Agent": "proyecto-academico-musica-caba (contacto: franco17cataldi@hotmail.com)"
}

SEGUNDOS_ENTRE_PEDIDOS = 1.0

DIRECTORIO_DATOS_CRUDOS = Path(__file__).resolve().parent.parent / "data" / "raw"


def listar_recursos_del_dataset(slug_del_dataset):
    """
    Consulta la API CKAN y devuelve los recursos (archivos) de un dataset.

    Objetivo
    --------
    No hardcodear las URLs de los CSV. Si el GCBA publica el año 2023, este
    script lo va a encontrar solo. Hardcodear las URLs significa que el script
    queda desactualizado en silencio.

    Pasos
    -----
    1. Armar la URL: {URL_BASE_API_CKAN}/package_show?id={slug_del_dataset}
    2. requests.get() con CABECERAS_HTTP y un timeout (¿qué pasa si el servidor
       no responde nunca y no ponés timeout?)
    3. Verificar el status code. requests tiene un método que levanta excepción
       si no es 2xx — buscalo, es una línea.
    4. Parsear el JSON de la respuesta
    5. La estructura es {"success": bool, "result": {"resources": [...]}}.
       Devolver esa lista de resources.

    Inputs
    ------
    slug_del_dataset : str
        El identificador del dataset, p.ej. "actividades-culturales".

    Devuelve
    --------
    list[dict], un dict por archivo, con claves como 'name', 'format', 'url'.
    """
    # TODO: implementar


def descargar_recurso_csv(url_del_recurso):
    """
    Descarga un CSV de BA Data y lo devuelve como DataFrame.

    Objetivo
    --------
    Traer el archivo crudo, sin transformar nada todavía. La regla del protocolo
    es guardar el crudo intacto: si se transforma y se guarda solo el resultado,
    un error descubierto después obliga a volver a descargar todo.

    Pasos
    -----
    1. Pedir la URL con requests. Las URLs de tipo /resource/<id>/download
       responden 302 y redirigen al CDN — requests sigue redirects por defecto,
       no hay que hacer nada especial.
    2. Verificar el status.
    3. Leer el contenido con pandas.
       OJO 1: el encoding. Los CSV del GCBA suelen venir en latin-1 o utf-8; si
       ves caracteres rotos en los nombres de barrios (Núñez, Villa Devoto),
       es eso.
       OJO 2: los faltantes vienen como el STRING "NA", no como campo vacío.
       Sin na_values=["NA"], pandas cree que la columna está llena de datos.
    4. Esperar SEGUNDOS_ENTRE_PEDIDOS antes de devolver, para no martillar el
       servidor cuando esta función se llame en loop.

    Inputs
    ------
    url_del_recurso : str

    Devuelve
    --------
    DataFrame con las columnas tal como vienen en el CSV, sin normalizar.
    """
    # TODO: implementar


def filtrar_eventos_de_musica(actividades_culturales):
    """
    Se queda solo con las filas cuya disciplina es música.

    Objetivo
    --------
    El dataset cubre todas las disciplinas del Ministerio de Cultura: artes
    visuales, cine, literatura, escénicas. El proyecto es sobre música.

    Pasos
    -----
    1. Mirar primero qué valores distintos toma la columna 'disciplina'.
       No asumas que dice exactamente "MÚSICA": puede tener acento o no, estar
       en minúsculas, tener espacios al final, o venir como "MUSICA / DANZA".
       Imprimí un value_counts() antes de filtrar.
    2. Normalizar antes de comparar (mayúsculas y acentos) para no perder filas
       por una tilde.
    3. Decidir qué hacer con 'MIXTO': ¿entra o no? Documentá la decisión.

    Inputs
    ------
    actividades_culturales : DataFrame
        Salida cruda de descargar_recurso_csv().

    Devuelve
    --------
    DataFrame con el mismo formato, filtrado.
    """
    # TODO: implementar


def normalizar_al_esquema_evento(actividades_de_musica, anio_del_recurso):
    """
    Convierte las filas de BA Data al contrato Evento de src/esquema.py.

    Objetivo
    --------
    Que todas las fuentes converjan al mismo formato. Este es el único lugar
    donde vive el conocimiento de "en BA Data el título está en 'actividad' y
    el venue en 'lugar'"; el resto del proyecto no necesita saberlo.

    Mapeo de columnas
    -----------------
        actividad            -> titulo
        lugar                -> venue_nombre
        direccion            -> venue_direccion
        lat                  -> venue_lat
        long                 -> venue_lon
        descripcion_actividad-> descripcion
        Links                -> url
        fecha_ini            -> fecha        (ver la decisión pendiente abajo)
        id                   -> se usa para generar el hash, no se guarda tal cual

    'artistas' no existe en esta fuente: dejar lista vacía. Se va a poder
    inferir del título en la Etapa 3.

    DECISIÓN PENDIENTE, tomala y documentala
    ----------------------------------------
    Hay filas donde fecha_ini y fecha_fin están separadas por meses: son
    muestras o ciclos largos, no un recital puntual. Tres opciones:
      (a) contar la actividad una sola vez, en fecha_ini
      (b) expandir a una fila por día del rango
      (c) filtrar por duración máxima y descartar las largas
    Afecta directamente los conteos del panel de la Etapa 4. Pensá qué representa
    mejor "la oferta de música en vivo de un barrio en un trimestre".

    Pasos
    -----
    1. Partir de dataframe_evento_vacio() para tener columnas y orden correctos
    2. Mapear cada columna
    3. pd.to_datetime() sobre las fechas — el validador rechaza strings
    4. Generar el id con generar_id_evento(NOMBRE_DE_LA_FUENTE, <algo estable>).
       ¿Qué usás como identificador? El dataset tiene columna 'id', pero se
       repite entre años. Pensá qué combinación identifica unívocamente una fila
       y no cambia si el GCBA reordena el archivo.
    5. scraped_at con marca_de_tiempo_de_scraping()

    Inputs
    ------
    actividades_de_musica : DataFrame
    anio_del_recurso : int
        De qué año es el archivo; puede hacer falta para el id.

    Devuelve
    --------
    DataFrame que cumple el esquema Evento.
    """
    # TODO: implementar


def main():
    """
    Orquesta la descarga completa y persiste el resultado.

    Todo el efecto secundario del script vive acá.

    Pasos
    -----
    1. Listar los recursos del dataset
    2. Quedarse con los CSV (hay XLSX, GeoJSON y SHP del mismo contenido)
    3. Para cada uno: descargar, filtrar música, normalizar
    4. Concatenar todo
    5. Excluir 2020 y 2021 — decisión del protocolo, § 2.
       ¿Lo hacés acá o en la Etapa 4? Argumento para hacerlo DESPUÉS: el crudo
       se guarda intacto y la exclusión es una decisión de análisis, no de
       adquisición. Argumento para hacerlo acá: menos datos que arrastrar.
       Mi recomendación es guardarlo todo y excluir en la Etapa 4, pero decidilo
       vos y dejá el comentario.
    6. validar_esquema_evento() ANTES de escribir. Si falla, no se escribe nada.
    7. Escribir a data/raw/ba_data_actividades_YYYYMMDD.parquet
    8. Imprimir un resumen: cuántos eventos, qué rango de fechas, cuántos barrios
       distintos. Sin esto no sabés si funcionó.
    """
    # TODO: implementar


if __name__ == "__main__":
    main()
