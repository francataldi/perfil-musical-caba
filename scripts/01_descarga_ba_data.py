import io
import sys
import time
import unicodedata
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.esquema import (
    dataframe_evento_vacio,
    generar_id_evento,
    marca_de_tiempo_de_scraping,
    validar_esquema_evento,
)

URL_BASE_API_CKAN = "https://data.buenosaires.gob.ar/api/3/action"
SLUG_DATASET = "actividades-culturales"
NOMBRE_DE_LA_FUENTE = "ba_data_actividades"

CABECERAS_HTTP = {"User-Agent": "musica-caba/1.0 (+https://github.com/francataldi/perfil-musical-caba)"}

SEGUNDOS_ENTRE_PEDIDOS = 1.0
SEGUNDOS_DE_ESPERA_MAXIMA = 90

DIRECTORIO_DATOS_CRUDOS = Path(__file__).resolve().parent.parent / "data" / "raw"

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

ANIOS_A_DESCARGAR = (2018, 2019, 2020, 2021, 2022)


def normalizar_texto_para_comparar(texto):
    texto_descompuesto = unicodedata.normalize("NFD", str(texto))
    texto_sin_acentos = "".join(caracter for caracter in texto_descompuesto if unicodedata.category(caracter) != "Mn")
    return texto_sin_acentos.upper().strip()


def resolver_nombre_de_columna(dataframe, nombres_posibles):
    for nombre_candidato in nombres_posibles:
        if nombre_candidato in dataframe.columns:
            return nombre_candidato
    return None


def listar_recursos_del_dataset(slug_del_dataset):
    respuesta = requests.get(
        f"{URL_BASE_API_CKAN}/package_show",
        params={"id": slug_del_dataset},
        headers=CABECERAS_HTTP,
        timeout=SEGUNDOS_DE_ESPERA_MAXIMA,
    )

    respuesta.raise_for_status()

    cuerpo_json = respuesta.json()
    if not cuerpo_json.get("success"):
        raise ValueError(f"CKAN respondió sin éxito para el dataset '{slug_del_dataset}'. Verificá que el slug exista en data.buenosaires.gob.ar.")

    time.sleep(SEGUNDOS_ENTRE_PEDIDOS)
    return cuerpo_json["result"]["resources"]


def seleccionar_recursos_csv_por_anio(recursos, anios_deseados):
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
    respuesta = requests.get(url_del_recurso, headers=CABECERAS_HTTP, timeout=SEGUNDOS_DE_ESPERA_MAXIMA)
    respuesta.raise_for_status()

    texto_del_csv = respuesta.content.decode("utf-8")

    tabla_cruda = pd.read_csv(
        io.StringIO(texto_del_csv),
        sep=None,
        engine="python",
        na_values=["NA", "N/A", "", "-"],
    )

    tabla_cruda.columns = [str(columna).strip() for columna in tabla_cruda.columns]

    time.sleep(SEGUNDOS_ENTRE_PEDIDOS)
    return tabla_cruda


def filtrar_eventos_de_musica(actividades_culturales):
    columna_de_disciplina = resolver_nombre_de_columna(actividades_culturales, NOMBRES_ALTERNATIVOS_POR_CAMPO["disciplina"])

    if columna_de_disciplina is None:
        raise ValueError(
            f"El archivo no tiene columna de disciplina, así que no se puede filtrar a música. Columnas presentes: {sorted(actividades_culturales.columns)}"
        )

    disciplinas_normalizadas = actividades_culturales[columna_de_disciplina].map(normalizar_texto_para_comparar)
    return actividades_culturales[disciplinas_normalizadas == "MUSICA"].copy()


def normalizar_al_esquema_evento(actividades_de_musica):
    columnas_encontradas = {
        campo: resolver_nombre_de_columna(actividades_de_musica, nombres_posibles) for campo, nombres_posibles in NOMBRES_ALTERNATIVOS_POR_CAMPO.items()
    }

    eventos = dataframe_evento_vacio()

    def tomar_columna(campo):
        nombre_real = columnas_encontradas[campo]
        if nombre_real is None:
            return pd.Series([None] * len(actividades_de_musica), dtype="object")
        return actividades_de_musica[nombre_real].reset_index(drop=True)

    fechas_de_inicio = pd.to_datetime(tomar_columna("fecha_inicio"), errors="coerce", dayfirst=True, format="mixed")
    titulos = tomar_columna("titulo")
    nombres_de_venue = tomar_columna("venue_nombre")

    claves_de_contenido = [
        f"{fecha}|{normalizar_texto_para_comparar(titulo)}|{normalizar_texto_para_comparar(venue)}"
        for fecha, titulo, venue in zip(fechas_de_inicio, titulos, nombres_de_venue, strict=True)
    ]

    eventos_normalizados = pd.DataFrame(
        {
            "id": [generar_id_evento(NOMBRE_DE_LA_FUENTE, clave) for clave in claves_de_contenido],
            "fuente": NOMBRE_DE_LA_FUENTE,
            "fecha": fechas_de_inicio,
            "titulo": titulos,
            "artistas": [[] for _ in range(len(actividades_de_musica))],
            "venue_nombre": nombres_de_venue,
            "venue_direccion": tomar_columna("venue_direccion"),
            "venue_lat": pd.to_numeric(tomar_columna("latitud"), errors="coerce"),
            "venue_lon": pd.to_numeric(tomar_columna("longitud"), errors="coerce"),
            "descripcion": tomar_columna("descripcion"),
            "url": tomar_columna("url"),
            "scraped_at": marca_de_tiempo_de_scraping(),
            "barrio_declarado_por_la_fuente": tomar_columna("barrio_declarado"),
        }
    )

    eventos_normalizados = eventos_normalizados.dropna(subset=["fecha", "venue_nombre"])

    return pd.concat([eventos, eventos_normalizados], ignore_index=True)


def main():
    print(f"Consultando la API CKAN para el dataset '{SLUG_DATASET}'...")
    recursos = listar_recursos_del_dataset(SLUG_DATASET)
    urls_de_csv_por_anio = seleccionar_recursos_csv_por_anio(recursos, ANIOS_A_DESCARGAR)
    print(f"Encontrados {len(urls_de_csv_por_anio)} CSV: {sorted(urls_de_csv_por_anio)}\n")

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

    cantidad_antes_de_deduplicar = len(eventos)
    eventos = eventos.drop_duplicates(subset=["id"], keep="first").reset_index(drop=True)
    print(
        f"\nDeduplicación entre archivos anuales: {cantidad_antes_de_deduplicar} -> "
        f"{len(eventos)} eventos "
        f"({cantidad_antes_de_deduplicar - len(eventos)} solapados)"
    )

    validar_esquema_evento(eventos)

    DIRECTORIO_DATOS_CRUDOS.mkdir(parents=True, exist_ok=True)
    marca_de_fecha = pd.Timestamp.now().strftime("%Y%m%d")
    ruta_de_salida = DIRECTORIO_DATOS_CRUDOS / f"ba_data_actividades_{marca_de_fecha}.parquet"
    eventos.to_parquet(ruta_de_salida, index=False)

    print(f"\n{'=' * 62}")
    print(f"Escrito: {ruta_de_salida.name}")
    print(f"Eventos de música:  {len(eventos)}")
    print(f"Rango de fechas:    {eventos['fecha'].min().date()} .. {eventos['fecha'].max().date()}")
    print(f"Venues distintos:   {eventos['venue_nombre'].nunique()}")
    print(f"Con coordenadas:    {eventos['venue_lat'].notna().sum()} ({eventos['venue_lat'].notna().mean():.1%})")
    print(f"{'=' * 62}")


if __name__ == "__main__":
    main()
