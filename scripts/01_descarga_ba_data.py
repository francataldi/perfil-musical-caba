"""
Descarga eventos musicales del portal de datos abiertos del GCBA (BA Data).

Fuente: data.buenosaires.gob.ar, portal CKAN. Sin key, sin login.
Inventario y cobertura medida en docs/01_fuentes.md.

ESTE ES UN SCRIPT, NO UNA LIBRERÍA. Toca la red y escribe a disco, así que todo
el efecto secundario vive dentro de main() y main() se llama solo desde el
bloque if __name__ == "__main__". Importarlo no puede disparar nada.

Uso:
    conda activate musica-caba
    python scripts/01_descarga_ba_data.py
"""

import io
import sys
import time
import unicodedata
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

# User-Agent honesto: identifica el proyecto para que quien administre el servidor
# pueda ver qué hacemos y contactarnos por el repo si le molesta. Se pone la URL
# del repositorio y NO un mail personal: un mail en texto plano en un repo público
# lo cosechan bots de spam en cuestión de días.
CABECERAS_HTTP = {
    "User-Agent": "musica-caba/1.0 (+https://github.com/francataldi/perfil-musical-caba)"
}

SEGUNDOS_ENTRE_PEDIDOS = 1.0
SEGUNDOS_DE_ESPERA_MAXIMA = 90

DIRECTORIO_DATOS_CRUDOS = Path(__file__).resolve().parent.parent / "data" / "raw"

# El GCBA cambió el esquema del dataset entre años: 2018-2019 usan un juego de
# nombres de columna y 2020-2022 usan otro para exactamente los mismos campos.
# Este diccionario traduce ambos a un vocabulario único, y es el único lugar del
# proyecto que conoce esa inconsistencia.
NOMBRES_ALTERNATIVOS_POR_CAMPO = {
    "titulo": ["actividad"],
    "venue_nombre": ["lugar", "establecimiento"],
    "venue_direccion": ["direccion", "dirección"],
    "descripcion": ["descripcion_actividad"],
    "fecha_inicio": ["fecha_ini", "fecha_inicio"],
    "fecha_fin": ["fecha_fin"],
    "disciplina": ["disciplina", "disciplina_artistica"],
    "barrio_declarado": ["barrio"],
    "latitud": ["lat"],
    "longitud": ["long"],
    "url": ["Links"],
    "id_nativo": ["id", "fid"],
}

# El archivo de 2017 (eventos-sspcyna.csv) tiene un esquema totalmente distinto:
# no trae columna de disciplina ni de fecha, así que no se puede filtrar a música
# ni ubicar en un trimestre. Se excluye y se documenta.
ANIOS_A_DESCARGAR = (2018, 2019, 2020, 2021, 2022)


def normalizar_texto_para_comparar(texto):
    """
    Normaliza un texto para poder compararlo sin que fallen tildes ni mayúsculas.

    Objetivo
    --------
    El valor de la columna de disciplina viene como "Música" en unos archivos y
    podría venir como "MUSICA" o "música " en otros. Comparar con == contra un
    literal pierde filas en silencio, que es la peor forma de perderlas: el
    script no falla, simplemente devuelve menos datos y nadie se entera.

    La descomposición NFD separa cada letra acentuada en (letra base + acento),
    y después se descartan los caracteres de categoría Mn (mark, nonspacing),
    que son exactamente los acentos. Así "Música" queda "MUSICA".

    Inputs
    ------
    texto : str o cualquier cosa convertible a str.

    Devuelve
    --------
    str en mayúsculas, sin tildes y sin espacios en los extremos.
    """
    texto_descompuesto = unicodedata.normalize("NFD", str(texto))
    texto_sin_acentos = "".join(
        caracter
        for caracter in texto_descompuesto
        if unicodedata.category(caracter) != "Mn"
    )
    return texto_sin_acentos.upper().strip()


def resolver_nombre_de_columna(dataframe, nombres_posibles):
    """
    Busca cuál de varios nombres alternativos existe realmente en el DataFrame.

    Objetivo
    --------
    Absorber el cambio de esquema entre años sin llenar el código de ifs. El
    resto del script pide "la columna de fecha de inicio" y esta función
    devuelve si en este archivo se llama 'fecha_ini' o 'fecha_inicio'.

    Inputs
    ------
    dataframe : DataFrame
    nombres_posibles : list[str]
        Alternativas, en orden de preferencia.

    Devuelve
    --------
    str con el nombre encontrado, o None si ninguno está presente.
    """
    for nombre_candidato in nombres_posibles:
        if nombre_candidato in dataframe.columns:
            return nombre_candidato
    return None


def listar_recursos_del_dataset(slug_del_dataset):
    """
    Consulta la API CKAN y devuelve los recursos (archivos) de un dataset.

    Objetivo
    --------
    No hardcodear las URLs de los CSV. Si el GCBA publica el año 2023, este
    script lo encuentra solo. Hardcodear las URLs significa quedar desactualizado
    en silencio.

    Inputs
    ------
    slug_del_dataset : str
        El identificador del dataset, p.ej. "actividades-culturales".

    Devuelve
    --------
    list[dict], un dict por archivo, con claves 'name', 'format' y 'url'.

    Raises
    ------
    requests.HTTPError si el servidor no responde 2xx.
    ValueError si CKAN responde pero marca la consulta como fallida.
    """
    # params= construye el query string con el escapado correcto. Concatenar a
    # mano se rompe con espacios, acentos y &.
    respuesta = requests.get(
        f"{URL_BASE_API_CKAN}/package_show",
        params={"id": slug_del_dataset},
        headers=CABECERAS_HTTP,
        timeout=SEGUNDOS_DE_ESPERA_MAXIMA,
    )

    # Sin esto un 404 NO falla: requests devuelve el objeto igual y seguirías
    # procesando una página de error como si fuera JSON válido.
    respuesta.raise_for_status()

    cuerpo_json = respuesta.json()
    if not cuerpo_json.get("success"):
        raise ValueError(
            f"CKAN respondió sin éxito para el dataset '{slug_del_dataset}'. "
            "Verificá que el slug exista en data.buenosaires.gob.ar."
        )

    time.sleep(SEGUNDOS_ENTRE_PEDIDOS)
    return cuerpo_json["result"]["resources"]


def seleccionar_recursos_csv_por_anio(recursos, anios_deseados):
    """
    Filtra la lista de recursos a los CSV de los años que interesan.

    Objetivo
    --------
    El dataset publica el mismo contenido en CSV, XLSX, GeoJSON y shapefile.
    Descargar los cuatro sería bajar todo cuatro veces. Se elige CSV porque es
    el formato más simple y el único presente en todos los años.

    El año no está en un campo propio: hay que extraerlo del nombre del recurso,
    que tiene la forma "Actividades Culturales 2019".

    Inputs
    ------
    recursos : list[dict]
        Salida de listar_recursos_del_dataset().
    anios_deseados : tuple[int]

    Devuelve
    --------
    dict {anio: url_del_csv}.
    """
    urls_de_csv_por_anio = {}

    for recurso in recursos:
        if recurso.get("format", "").upper() != "CSV":
            continue

        nombre_del_recurso = recurso.get("name", "")
        for anio in anios_deseados:
            if str(anio) in nombre_del_recurso:
                urls_de_csv_por_anio[anio] = recurso["url"]
                break

    return urls_de_csv_por_anio


def descargar_recurso_csv(url_del_recurso):
    """
    Descarga un CSV de BA Data y lo devuelve como DataFrame, sin transformar.

    Objetivo
    --------
    Traer el archivo crudo tal como llega. La regla del protocolo es guardar el
    crudo intacto: si se transforma y se persiste solo el resultado, un error
    descubierto después obliga a volver a descargar todo.

    Inputs
    ------
    url_del_recurso : str
        Puede ser la URL del CDN o la de CKAN con /download, que responde 302 y
        redirige. requests sigue redirects por defecto, no hay que hacer nada.

    Devuelve
    --------
    DataFrame con las columnas tal como vienen, con los nombres ya sin espacios
    sobrantes en los extremos.

    Raises
    ------
    requests.HTTPError si el servidor no responde 2xx.
    """
    respuesta = requests.get(
        url_del_recurso, headers=CABECERAS_HTTP, timeout=SEGUNDOS_DE_ESPERA_MAXIMA
    )
    respuesta.raise_for_status()

    # Se decodifica explícitamente en vez de usar respuesta.text porque requests
    # adivina el encoding y se equivoca seguido con archivos en español. El
    # síntoma es ver "NÃºÃ±ez" donde debería decir "Núñez".
    texto_del_csv = respuesta.content.decode("utf-8")

    # sep=None + engine="python" hace que pandas detecte solo si el separador es
    # coma o punto y coma, que varía entre archivos del GCBA.
    # na_values=["NA"] es imprescindible: los faltantes vienen como el STRING
    # "NA", y sin esto pandas cree que la columna está llena de datos.
    tabla_cruda = pd.read_csv(
        io.StringIO(texto_del_csv),
        sep=None,
        engine="python",
        na_values=["NA", "N/A", "", "-"],
    )

    # El archivo de 2019 tiene la columna 'barrio ' con un espacio al final.
    # Sin este strip, df["barrio"] tira KeyError y cuesta media hora entender
    # por qué, porque el espacio es invisible al imprimir las columnas.
    tabla_cruda.columns = [str(columna).strip() for columna in tabla_cruda.columns]

    time.sleep(SEGUNDOS_ENTRE_PEDIDOS)
    return tabla_cruda


def filtrar_eventos_de_musica(actividades_culturales):
    """
    Se queda solo con las filas cuya disciplina artística es música.

    Objetivo
    --------
    El dataset cubre todas las disciplinas del Ministerio de Cultura: artes
    escénicas, visuales, cine, literatura, diseño, gastronomía. El proyecto es
    sobre música.

    Decisión tomada: 'Mixto' NO entra. Es una categoría que agrupa eventos
    multidisciplinarios donde la música puede ser secundaria o inexistente.
    Incluirla metería ruido en un target que ya es una variable construida.
    La contrapartida es que se pierden festivales que sí tienen música, y eso
    va documentado como sesgo conocido en la sección de limitaciones.

    Inputs
    ------
    actividades_culturales : DataFrame
        Salida cruda de descargar_recurso_csv().

    Devuelve
    --------
    DataFrame filtrado, mismas columnas.
    """
    columna_de_disciplina = resolver_nombre_de_columna(
        actividades_culturales, NOMBRES_ALTERNATIVOS_POR_CAMPO["disciplina"]
    )

    if columna_de_disciplina is None:
        raise ValueError(
            "El archivo no tiene columna de disciplina, así que no se puede "
            f"filtrar a música. Columnas presentes: "
            f"{sorted(actividades_culturales.columns)}"
        )

    disciplinas_normalizadas = actividades_culturales[columna_de_disciplina].map(
        normalizar_texto_para_comparar
    )
    return actividades_culturales[disciplinas_normalizadas == "MUSICA"].copy()


def normalizar_al_esquema_evento(actividades_de_musica):
    """
    Convierte filas de BA Data al contrato Evento de src/esquema.py.

    Objetivo
    --------
    Que todas las fuentes converjan al mismo formato. Este es el único lugar del
    proyecto donde vive el conocimiento de que en BA Data el título está en
    'actividad' y el venue en 'lugar' o 'establecimiento' según el año.

    Decisión sobre actividades de larga duración
    --------------------------------------------
    Cada actividad se cuenta UNA SOLA VEZ, en su fecha de inicio. No se expande
    a una fila por día del rango, por dos razones:

    1. 'fecha_fin' solo existe en los archivos de 2020 en adelante. Expandir
       inflaría 2020-2022 y dejaría 2018-2019 sin tocar, creando un salto de
       oferta musical que sería un artefacto del cambio de formato del archivo,
       no un fenómeno real. El panel leería eso como tendencia.
    2. Un ciclo semanal de tres meses no ocurre 90 días: ocurre unas 12 veces.
       Expandir por día lo contaría 90.

    Inputs
    ------
    actividades_de_musica : DataFrame
        Salida de filtrar_eventos_de_musica().
    Devuelve
    --------
    DataFrame que cumple el esquema Evento.

    Decisión sobre el identificador
    -------------------------------
    El hash se construye del CONTENIDO que identifica al evento
    (fecha + título + venue), no de la columna 'id' del archivo.

    Motivo: esa columna vale 1, 2, 3, ... N. Es un número de fila, no un
    identificador estable. Si el GCBA republica el archivo con las filas
    reordenadas, todos los ids cambian y el scraper deja de ser idempotente
    entre descargas: la segunda corrida vería 5.000 eventos "nuevos".

    Como beneficio adicional, los archivos anuales se solapan (el de 2019 llega
    a diciembre de 2020, el de 2022 arranca en enero de 2021) y con un hash de
    contenido el mismo evento recibe el mismo id en ambos, así que la
    deduplicación entre archivos sale sola.
    """
    columnas_encontradas = {
        campo: resolver_nombre_de_columna(actividades_de_musica, nombres_posibles)
        for campo, nombres_posibles in NOMBRES_ALTERNATIVOS_POR_CAMPO.items()
    }

    eventos = dataframe_evento_vacio()

    def tomar_columna(campo):
        # Devuelve la columna si existe en este archivo, o una serie de nulos si
        # el campo no está presente ese año. Evita KeyError sin llenar de ifs.
        nombre_real = columnas_encontradas[campo]
        if nombre_real is None:
            return pd.Series([None] * len(actividades_de_musica), dtype="object")
        return actividades_de_musica[nombre_real].reset_index(drop=True)

    fechas_de_inicio = pd.to_datetime(
        tomar_columna("fecha_inicio"), errors="coerce", dayfirst=True, format="mixed"
    )
    titulos = tomar_columna("titulo")
    nombres_de_venue = tomar_columna("venue_nombre")

    # La clave del hash es el contenido que identifica al evento, no la columna
    # 'id' del archivo (que es un número de fila y cambia si reordenan las filas).
    claves_de_contenido = [
        f"{fecha}|{normalizar_texto_para_comparar(titulo)}"
        f"|{normalizar_texto_para_comparar(venue)}"
        # strict=True hace que zip falle si las tres series no tienen el mismo
        # largo. Sin eso, un desalineamiento truncaría en silencio al más corto.
        for fecha, titulo, venue in zip(
            fechas_de_inicio, titulos, nombres_de_venue, strict=True
        )
    ]

    eventos_normalizados = pd.DataFrame(
        {
            "id": [
                generar_id_evento(NOMBRE_DE_LA_FUENTE, clave)
                for clave in claves_de_contenido
            ],
            "fuente": NOMBRE_DE_LA_FUENTE,
            "fecha": fechas_de_inicio,
            "titulo": titulos,
            # BA Data no desagrega artistas. Se deja lista vacía; en la Etapa 3
            # se intentará inferirlos del título.
            "artistas": [[] for _ in range(len(actividades_de_musica))],
            "venue_nombre": nombres_de_venue,
            "venue_direccion": tomar_columna("venue_direccion"),
            "venue_lat": pd.to_numeric(tomar_columna("latitud"), errors="coerce"),
            "venue_lon": pd.to_numeric(tomar_columna("longitud"), errors="coerce"),
            "descripcion": tomar_columna("descripcion"),
            "url": tomar_columna("url"),
            "scraped_at": marca_de_tiempo_de_scraping(),
            # Columna extra al esquema Evento, a propósito. NO se usa como
            # verdad: el barrio se re-deriva por point-in-polygon en la Etapa 2
            # para tener criterio homogéneo entre fuentes. Se conserva como
            # CONTROL CRUZADO del spatial join: si el 95% coincide, el join está
            # bien; si coincide el 60%, hay un problema de CRS o de shapefile.
            # Es una validación gratis que solo esta fuente puede aportar.
            "barrio_declarado_por_la_fuente": tomar_columna("barrio_declarado"),
        }
    )

    # El validador exige venue_nombre no nulo: sin venue no hay barrio posible.
    # Se descartan acá y se reporta cuántas, en vez de dejar que explote después.
    eventos_normalizados = eventos_normalizados.dropna(subset=["fecha", "venue_nombre"])

    return pd.concat([eventos, eventos_normalizados], ignore_index=True)


def main():
    """
    Orquesta la descarga completa y persiste el resultado crudo.

    Todo el efecto secundario del script vive acá: red, disco y prints.
    """
    print(f"Consultando la API CKAN para el dataset '{SLUG_DATASET}'...")
    recursos = listar_recursos_del_dataset(SLUG_DATASET)
    urls_de_csv_por_anio = seleccionar_recursos_csv_por_anio(
        recursos, ANIOS_A_DESCARGAR
    )
    print(f"Encontrados {len(urls_de_csv_por_anio)} CSV: "
          f"{sorted(urls_de_csv_por_anio)}\n")

    eventos_por_anio = []
    for anio in sorted(urls_de_csv_por_anio):
        tabla_cruda = descargar_recurso_csv(urls_de_csv_por_anio[anio])
        actividades_de_musica = filtrar_eventos_de_musica(tabla_cruda)
        eventos_del_anio = normalizar_al_esquema_evento(actividades_de_musica)
        eventos_por_anio.append(eventos_del_anio)

        print(
            f"  {anio}: {len(tabla_cruda):>6} filas totales -> "
            f"{len(actividades_de_musica):>5} de música -> "
            f"{len(eventos_del_anio):>5} con fecha y venue válidos"
        )

    eventos = pd.concat(eventos_por_anio, ignore_index=True)

    # Los archivos anuales se pisan entre sí: el de 2019 llega hasta diciembre
    # de 2020 y el de 2022 arranca en enero de 2021. Como el id es un hash del
    # contenido, el mismo evento recibe el mismo id en ambos archivos y la
    # deduplicación es simplemente quedarse con ids únicos.
    cantidad_antes_de_deduplicar = len(eventos)
    eventos = eventos.drop_duplicates(subset=["id"], keep="first").reset_index(
        drop=True
    )
    print(
        f"\nDeduplicación entre archivos anuales: {cantidad_antes_de_deduplicar} -> "
        f"{len(eventos)} eventos "
        f"({cantidad_antes_de_deduplicar - len(eventos)} solapados)"
    )

    # NO se excluyen 2020-2021 acá. El protocolo los excluye del PANEL, que es
    # una decisión de análisis (Etapa 4), no de adquisición. El crudo se guarda
    # completo: si mañana se revisa esa decisión, no hay que re-descargar nada.
    validar_esquema_evento(eventos)

    DIRECTORIO_DATOS_CRUDOS.mkdir(parents=True, exist_ok=True)
    marca_de_fecha = pd.Timestamp.now().strftime("%Y%m%d")
    ruta_de_salida = (
        DIRECTORIO_DATOS_CRUDOS / f"ba_data_actividades_{marca_de_fecha}.parquet"
    )
    eventos.to_parquet(ruta_de_salida, index=False)

    print(f"\n{'=' * 62}")
    print(f"Escrito: {ruta_de_salida.name}")
    print(f"Eventos de música:  {len(eventos)}")
    print(f"Rango de fechas:    {eventos['fecha'].min().date()} .. "
          f"{eventos['fecha'].max().date()}")
    print(f"Venues distintos:   {eventos['venue_nombre'].nunique()}")
    print(f"Con coordenadas:    {eventos['venue_lat'].notna().sum()} "
          f"({eventos['venue_lat'].notna().mean():.1%})")
    print(f"{'=' * 62}")


if __name__ == "__main__":
    main()
