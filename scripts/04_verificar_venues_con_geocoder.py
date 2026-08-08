"""
Verificación INDEPENDIENTE del barrio asignado a cada venue del top 30.

Qué hace y por qué no reemplaza a la verificación manual
---------------------------------------------------------
Toma la DIRECCIÓN de texto de cada venue —un campo que el spatial join nunca
usó— la geocodifica contra Nominatim (OpenStreetMap, una fuente distinta de
BA Data) y comprueba si el punto resultante cae en el mismo barrio que asignó
el point-in-polygon.

Es una verificación real, no una copia del dato original: si BA Data tuviera la
coordenada equivocada, Nominatim la geocodificaría en otro lado y la
discrepancia saltaría. Pero verifica algo distinto que el ojo humano:

    - El geocoder detecta COORDENADAS MAL PUESTAS.
    - La persona detecta que un NOMBRE AGRUPA VARIAS SEDES, que ningún
      método automático puede ver.

Los dos métodos fallan en casos distintos, así que se registran por separado en
la columna 'metodo_de_verificacion' y nunca se mezclan. Una celda verificada por
el geocoder NO cuenta como verificada a mano.

Ética de uso de Nominatim
-------------------------
Es un servicio gratuito sostenido por donaciones. Su política de uso pide
máximo 1 pedido por segundo y un User-Agent identificable. Se respetan ambas.
Son ~20 pedidos, así que el costo para ellos es despreciable.

Uso:
    conda activate musica-caba
    python scripts/04_verificar_venues_con_geocoder.py
"""

import re
import sys
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.normalizacion import normalizar_texto_para_comparar  # noqa: E402

URL_NOMINATIM = "https://nominatim.openstreetmap.org/search"

# Nominatim exige un User-Agent identificable; los pedidos anónimos los bloquea.
CABECERAS_HTTP = {
    "User-Agent": "musica-caba/1.0 (+https://github.com/francataldi/perfil-musical-caba)"
}

# La política de uso de Nominatim pide un máximo de 1 pedido por segundo.
SEGUNDOS_ENTRE_PEDIDOS = 1.1

CRS_ALMACENAMIENTO = "EPSG:4326"
CRS_METRICO = "EPSG:5347"

RAIZ_DEL_PROYECTO = Path(__file__).resolve().parent.parent
DIRECTORIO_CRUDO = RAIZ_DEL_PROYECTO / "data" / "raw"
DIRECTORIO_INTERMEDIO = RAIZ_DEL_PROYECTO / "data" / "interim"

RUTA_PLANILLA = DIRECTORIO_INTERMEDIO / "verificacion_venues.csv"
RUTA_PLANILLA_COMPLETA = DIRECTORIO_INTERMEDIO / "verificacion_venues_completa.csv"

NOMBRES_POSIBLES_DE_COLUMNA_BARRIO = ["BARRIO", "barrio", "nombre", "NOMBRE"]

# Distancia a partir de la cual la discrepancia entre la coordenada de BA Data y
# la de Nominatim deja de ser ruido de geocodificación y pasa a ser sospechosa.
# 500 m es aproximadamente cinco cuadras porteñas: más que eso ya no se explica
# por imprecisión de altura catastral.
METROS_DE_DISCREPANCIA_ACEPTABLE = 500


def desinvertir_nombre_de_calle(direccion):
    """
    Traduce el formato catastral del GCBA al orden natural de lectura.

    Objetivo
    --------
    El GCBA escribe las calles con apellido primero y las partes separadas por
    comas, como en un índice alfabético:

        "ARTIGAS, JOSE GERVASIO, GRAL. 2262"  ->  "GRAL. JOSE GERVASIO ARTIGAS 2262"
        "ISABEL, INFANTA AV. 555"             ->  "AV. INFANTA ISABEL 555"
        "PERON, EVA AV. 1400"                 ->  "AV. EVA PERON 1400"

    Nominatim no entiende ese formato y devuelve vacío, lo que hacía fallar la
    verificación de 4 de los 30 venues. La causa no era ni un error de los datos
    ni una limitación del geocoder: era una convención de escritura sin traducir.

    Cómo funciona
    -------------
    1. Se separa la ALTURA (el número final) del nombre de la calle. Este paso
       es imprescindible: la altura viaja pegada a la última parte, así que
       invertir sin extraerla primero la deja enterrada en el medio
       ("MARECHAL, LEOPOLDO 832" daría "LEOPOLDO 832 MARECHAL").
    2. Se invierte el orden de las partes separadas por coma.
    3. Se vuelve a pegar la altura al final, que es donde corresponde.

    Las direcciones sin comas ("CERRITO 628") se devuelven intactas: ya están
    en orden natural.

    Inputs
    ------
    direccion : str

    Devuelve
    --------
    str con las partes reordenadas y la altura al final.
    """
    direccion_limpia = direccion.replace(", CABA", "").strip()

    if "," not in direccion_limpia:
        return direccion_limpia

    coincidencia_de_altura = re.search(r"\s(\d+)\s*$", direccion_limpia)
    altura = coincidencia_de_altura.group(1) if coincidencia_de_altura else ""
    if coincidencia_de_altura:
        direccion_limpia = direccion_limpia[: coincidencia_de_altura.start()]

    partes = [parte.strip() for parte in direccion_limpia.split(",") if parte.strip()]
    nombre_de_calle = " ".join(reversed(partes))

    return f"{nombre_de_calle} {altura}".strip()


def geocodificar_direccion_en_caba(direccion):
    """
    Geocodifica una dirección porteña contra Nominatim (OpenStreetMap).

    Objetivo
    --------
    Obtener una coordenada de una fuente INDEPENDIENTE de BA Data, para poder
    contrastar. Si se usara el mismo dato de origen, la comparación no
    verificaría nada.

    Se acota la búsqueda a Argentina con countrycodes y se agrega
    "Ciudad Autónoma de Buenos Aires" al texto, porque muchas calles porteñas
    tienen homónimas en otras ciudades del país y sin acotar el geocoder puede
    devolver un punto en Córdoba con toda confianza.

    Inputs
    ------
    direccion : str
        La dirección tal como viene en los datos, p.ej. "CERRITO 628".

    Devuelve
    --------
    tuple (latitud, longitud) o (None, None) si no encontró nada.
    """
    direccion_en_orden_natural = desinvertir_nombre_de_calle(direccion)
    consulta = (
        f"{direccion_en_orden_natural}, Ciudad Autónoma de Buenos Aires, Argentina"
    )

    respuesta = requests.get(
        URL_NOMINATIM,
        params={
            "q": consulta,
            "format": "json",
            "limit": 1,
            "countrycodes": "ar",
        },
        headers=CABECERAS_HTTP,
        timeout=30,
    )
    respuesta.raise_for_status()

    resultados = respuesta.json()
    time.sleep(SEGUNDOS_ENTRE_PEDIDOS)

    if not resultados:
        return None, None

    return float(resultados[0]["lat"]), float(resultados[0]["lon"])


def cargar_barrios():
    """
    Carga los polígonos oficiales de barrios descargados en la Etapa 2.

    Devuelve
    --------
    tuple (GeoDataFrame, nombre_de_la_columna_de_barrio)
    """
    barrios = gpd.read_file(DIRECTORIO_CRUDO / "barrios_caba.geojson")

    for nombre_candidato in NOMBRES_POSIBLES_DE_COLUMNA_BARRIO:
        if nombre_candidato in barrios.columns:
            return barrios.to_crs(CRS_ALMACENAMIENTO), nombre_candidato

    raise ValueError(f"No encuentro la columna de barrio en {list(barrios.columns)}")


def ubicar_punto_en_barrio(latitud, longitud, barrios, columna_de_barrio):
    """
    Determina en qué barrio cae un punto suelto.

    Objetivo
    --------
    Aplicar el mismo criterio de point-in-polygon que usó la Etapa 2, pero sobre
    la coordenada que devolvió el geocoder independiente. Usar el mismo criterio
    es lo que hace comparables los dos resultados: si se usara otro, no se
    sabría si la diferencia viene del dato o del método.

    Inputs
    ------
    latitud, longitud : float
    barrios : GeoDataFrame
    columna_de_barrio : str

    Devuelve
    --------
    str con el nombre del barrio, o None si el punto cae fuera de CABA.
    """
    if latitud is None or longitud is None:
        return None

    punto = gpd.points_from_xy([longitud], [latitud])[0]
    contiene_al_punto = barrios.geometry.contains(punto)

    if not contiene_al_punto.any():
        return None

    return barrios.loc[contiene_al_punto, columna_de_barrio].iat[0]


def medir_distancia_en_metros(latitud_a, longitud_a, latitud_b, longitud_b):
    """
    Distancia entre dos puntos, en metros.

    Objetivo
    --------
    Cuantificar cuánto se apartó el geocoder de la coordenada original. Es la
    magnitud lo que dice qué tipo de problema hay: 50 m es imprecisión de
    altura catastral, 5 km es otro lugar.

    Se reproyecta a EPSG:5347 porque en EPSG:4326 la resta daría grados, y un
    grado no mide lo mismo en latitud que en longitud.

    Inputs
    ------
    latitud_a, longitud_a, latitud_b, longitud_b : float

    Devuelve
    --------
    float con la distancia en metros, o None si falta alguna coordenada.
    """
    if None in (latitud_a, longitud_a, latitud_b, longitud_b):
        return None

    puntos = gpd.GeoSeries(
        gpd.points_from_xy([longitud_a, longitud_b], [latitud_a, latitud_b]),
        crs=CRS_ALMACENAMIENTO,
    ).to_crs(CRS_METRICO)

    return float(puntos.iloc[0].distance(puntos.iloc[1]))


def main():
    """Orquesta la verificación independiente y escribe la planilla completa."""
    print("=" * 76)
    print("VERIFICACIÓN INDEPENDIENTE DE VENUES — geocoder Nominatim (OpenStreetMap)")
    print("=" * 76)

    if not RUTA_PLANILLA.exists():
        raise FileNotFoundError(
            f"Falta {RUTA_PLANILLA.name}. Corré antes scripts/03_verificar_venues.py"
        )

    planilla = pd.read_csv(RUTA_PLANILLA, encoding="utf-8-sig")
    barrios, columna_de_barrio = cargar_barrios()

    # Las filas que Franco ya verificó a mano NO se tocan: su juicio sobre si un
    # nombre agrupa varias sedes es información que el geocoder no puede producir.
    ya_verificadas_a_mano = planilla["es_correcto"].notna() & (
        planilla["es_correcto"].astype(str).str.strip() != ""
    )
    print(
        f"\nVerificadas a mano: {ya_verificadas_a_mano.sum()} de {len(planilla)} "
        f"({planilla.loc[ya_verificadas_a_mano, 'n_eventos'].sum()} eventos, "
        f"{planilla.loc[ya_verificadas_a_mano, 'n_eventos'].sum() / planilla['n_eventos'].sum():.1%} "
        "del top 30)"
    )
    print(f"A geocodificar:     {(~ya_verificadas_a_mano).sum()}\n")

    planilla["metodo_de_verificacion"] = ""
    planilla.loc[ya_verificadas_a_mano, "metodo_de_verificacion"] = "manual"

    planilla["barrio_segun_geocoder"] = None
    planilla["metros_entre_geocoder_y_fuente"] = None

    print("-" * 76)
    print(f"{'VENUE':<40} {'BA DATA':<18} {'NOMINATIM':<18}")
    print("-" * 76)

    filas_a_geocodificar = planilla.index[~ya_verificadas_a_mano]
    for indice in filas_a_geocodificar:
        fila = planilla.loc[indice]

        latitud_geocoder, longitud_geocoder = geocodificar_direccion_en_caba(
            str(fila["direccion_mas_comun"])
        )
        barrio_segun_geocoder = ubicar_punto_en_barrio(
            latitud_geocoder, longitud_geocoder, barrios, columna_de_barrio
        )
        distancia = medir_distancia_en_metros(
            fila["latitud_mediana"],
            fila["longitud_mediana"],
            latitud_geocoder,
            longitud_geocoder,
        )

        planilla.at[indice, "barrio_segun_geocoder"] = barrio_segun_geocoder
        planilla.at[indice, "metros_entre_geocoder_y_fuente"] = (
            round(distancia) if distancia is not None else None
        )
        planilla.at[indice, "metodo_de_verificacion"] = "geocoder_nominatim"

        coinciden = normalizar_texto_para_comparar(
            barrio_segun_geocoder
        ) == normalizar_texto_para_comparar(fila["barrio_asignado"])

        planilla.at[indice, "es_correcto"] = (
            "SI (geocoder)" if coinciden else "REVISAR"
        )
        planilla.at[indice, "barrio_verificado_a_mano"] = ""

        marca = "  " if coinciden else " <"
        distancia_texto = f"{distancia:>6.0f}m" if distancia is not None else "   s/d"
        print(
            f"{fila['venue_normalizado'][:38]:<40} "
            f"{str(fila['barrio_asignado'])[:16]:<18} "
            f"{str(barrio_segun_geocoder)[:16]:<18} {distancia_texto}{marca}"
        )

    planilla.to_csv(RUTA_PLANILLA_COMPLETA, index=False, encoding="utf-8-sig")

    geocodificadas = planilla["metodo_de_verificacion"] == "geocoder_nominatim"
    a_revisar = planilla["es_correcto"].astype(str).str.contains("REVISAR")

    print("\n" + "=" * 76)
    print("RESUMEN")
    print(f"  verificadas a mano:        {ya_verificadas_a_mano.sum():>3}")
    print(f"  verificadas por geocoder:  {geocodificadas.sum():>3}")
    print(f"  discrepancias a revisar:   {a_revisar.sum():>3}")

    if a_revisar.any():
        print("\n  Casos que necesitan ojo humano:")
        for _, fila in planilla[a_revisar].iterrows():
            print(
                f"    {fila['venue_normalizado'][:36]:<38} "
                f"BA Data: {fila['barrio_asignado']:<18} "
                f"OSM: {fila['barrio_segun_geocoder']}"
            )
        print(
            "\n  Una discrepancia NO significa que BA Data esté mal: Nominatim\n"
            "  también se equivoca, sobre todo con esquinas y direcciones sin\n"
            "  altura. Es una señal de dónde mirar, no un veredicto."
        )

    print(f"\nEscrito: {RUTA_PLANILLA_COMPLETA.name}")
    print("=" * 76)


if __name__ == "__main__":
    main()
