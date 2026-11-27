import numpy as np
import pandas as pd
import pytest

from src.esquema import (
    COLUMNAS_EVENTO,
    dataframe_evento_vacio,
    generar_id_evento,
    marca_de_tiempo_de_scraping,
    validar_esquema_evento,
)


def construir_eventos_validos(cantidad_de_filas=3):
    eventos = dataframe_evento_vacio()
    momento_del_scraping = marca_de_tiempo_de_scraping()

    filas = []
    for indice in range(cantidad_de_filas):
        filas.append(
            {
                "id": generar_id_evento("fuente_de_prueba", f"evento-{indice}"),
                "fuente": "fuente_de_prueba",
                "fecha": pd.Timestamp("2019-03-15") + pd.Timedelta(days=indice),
                "titulo": f"Recital {indice}",
                "artistas": ["Artista A", "Artista B"],
                "venue_nombre": "Niceto Club",
                "venue_direccion": "Niceto Vega 5510",
                "venue_lat": -34.5875,
                "venue_lon": -58.4368,
                "descripcion": None,
                "url": "https://ejemplo.test/evento",
                "scraped_at": momento_del_scraping,
            }
        )

    return pd.concat([eventos, pd.DataFrame(filas)], ignore_index=True).astype({"fecha": "datetime64[ns]", "scraped_at": "datetime64[ns]"})


def test_el_hash_es_determinista():
    primera_llamada = generar_id_evento("ba_data", "actividad-1234")
    segunda_llamada = generar_id_evento("ba_data", "actividad-1234")

    assert primera_llamada == segunda_llamada


def test_el_hash_distingue_entradas_distintas():
    assert generar_id_evento("ba_data", "a") != generar_id_evento("ba_data", "b")


def test_el_hash_distingue_fuentes():
    assert generar_id_evento("ba_data", "42") != generar_id_evento("songkick", "42")


def test_el_hash_tiene_longitud_fija():
    assert len(generar_id_evento("ba_data", "cualquier-cosa")) == 16


def test_el_hash_no_colisiona_en_volumen_realista():
    identificadores = {generar_id_evento("ba_data", f"evento-{indice}") for indice in range(20_000)}

    assert len(identificadores) == 20_000


def test_la_marca_de_tiempo_es_naive_y_compatible_con_parquet():
    assert marca_de_tiempo_de_scraping().tzinfo is None


def test_la_marca_de_tiempo_avanza():
    primera = marca_de_tiempo_de_scraping()
    segunda = marca_de_tiempo_de_scraping()

    assert segunda >= primera


def test_el_dataframe_vacio_tiene_todas_las_columnas_en_orden():
    dataframe_vacio = dataframe_evento_vacio()

    assert list(dataframe_vacio.columns) == list(COLUMNAS_EVENTO)
    assert len(dataframe_vacio) == 0


def test_acepta_un_dataframe_valido():
    validar_esquema_evento(construir_eventos_validos())


def test_rechaza_columnas_faltantes():
    eventos_incompletos = construir_eventos_validos().drop(columns=["venue_lat"])

    with pytest.raises(ValueError, match="Faltan columnas"):
        validar_esquema_evento(eventos_incompletos)


def test_rechaza_nulos_en_columnas_obligatorias():
    eventos_con_venue_nulo = construir_eventos_validos()
    eventos_con_venue_nulo.loc[0, "venue_nombre"] = None

    with pytest.raises(ValueError, match="venue_nombre"):
        validar_esquema_evento(eventos_con_venue_nulo)


def test_rechaza_fechas_como_texto():
    eventos_con_fecha_texto = construir_eventos_validos()
    eventos_con_fecha_texto["fecha"] = eventos_con_fecha_texto["fecha"].astype(str)

    with pytest.raises(ValueError, match="fecha"):
        validar_esquema_evento(eventos_con_fecha_texto)


def test_rechaza_ids_duplicados():
    eventos_con_id_repetido = construir_eventos_validos()
    eventos_con_id_repetido.loc[1, "id"] = eventos_con_id_repetido.loc[0, "id"]

    with pytest.raises(ValueError, match="duplicados"):
        validar_esquema_evento(eventos_con_id_repetido)


def test_permite_coordenadas_nulas_por_defecto():
    eventos_sin_coordenadas = construir_eventos_validos()
    eventos_sin_coordenadas["venue_lat"] = np.nan
    eventos_sin_coordenadas["venue_lon"] = np.nan

    validar_esquema_evento(eventos_sin_coordenadas)


def test_rechaza_coordenadas_nulas_cuando_se_exigen():
    eventos_sin_coordenadas = construir_eventos_validos()
    eventos_sin_coordenadas["venue_lat"] = np.nan

    with pytest.raises(ValueError, match="venue_lat"):
        validar_esquema_evento(eventos_sin_coordenadas, permitir_coordenadas_nulas=False)


def test_detecta_latitud_y_longitud_invertidas():
    eventos_con_coordenadas_invertidas = construir_eventos_validos()
    eventos_con_coordenadas_invertidas["venue_lat"] = -58.4368
    eventos_con_coordenadas_invertidas["venue_lon"] = -34.5875

    with pytest.raises(ValueError, match="invertidas"):
        validar_esquema_evento(eventos_con_coordenadas_invertidas)
