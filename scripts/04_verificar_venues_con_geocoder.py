import re
import sys
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.normalizacion import normalizar_texto_para_comparar

URL_NOMINATIM = "https://nominatim.openstreetmap.org/search"

CABECERAS_HTTP = {"User-Agent": "musica-caba/1.0 (+https://github.com/francataldi/perfil-musical-caba)"}

SEGUNDOS_ENTRE_PEDIDOS = 1.1

CRS_ALMACENAMIENTO = "EPSG:4326"
CRS_METRICO = "EPSG:5347"

RAIZ_DEL_PROYECTO = Path(__file__).resolve().parent.parent
DIRECTORIO_CRUDO = RAIZ_DEL_PROYECTO / "data" / "raw"
DIRECTORIO_INTERMEDIO = RAIZ_DEL_PROYECTO / "data" / "interim"

RUTA_PLANILLA = DIRECTORIO_INTERMEDIO / "verificacion_venues.csv"
RUTA_PLANILLA_COMPLETA = DIRECTORIO_INTERMEDIO / "verificacion_venues_completa.csv"

NOMBRES_POSIBLES_DE_COLUMNA_BARRIO = ["BARRIO", "barrio", "nombre", "NOMBRE"]

METROS_DE_DISCREPANCIA_ACEPTABLE = 500


def desinvertir_nombre_de_calle(direccion):
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
    direccion_en_orden_natural = desinvertir_nombre_de_calle(direccion)
    consulta = f"{direccion_en_orden_natural}, Ciudad Autónoma de Buenos Aires, Argentina"

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
    barrios = gpd.read_file(DIRECTORIO_CRUDO / "barrios_caba.geojson")

    for nombre_candidato in NOMBRES_POSIBLES_DE_COLUMNA_BARRIO:
        if nombre_candidato in barrios.columns:
            return barrios.to_crs(CRS_ALMACENAMIENTO), nombre_candidato

    raise ValueError(f"No encuentro la columna de barrio en {list(barrios.columns)}")


def ubicar_punto_en_barrio(latitud, longitud, barrios, columna_de_barrio):
    if latitud is None or longitud is None:
        return None

    punto = gpd.points_from_xy([longitud], [latitud])[0]
    contiene_al_punto = barrios.geometry.contains(punto)

    if not contiene_al_punto.any():
        return None

    return barrios.loc[contiene_al_punto, columna_de_barrio].iat[0]


def medir_distancia_en_metros(latitud_a, longitud_a, latitud_b, longitud_b):
    if None in (latitud_a, longitud_a, latitud_b, longitud_b):
        return None

    puntos = gpd.GeoSeries(
        gpd.points_from_xy([longitud_a, longitud_b], [latitud_a, latitud_b]),
        crs=CRS_ALMACENAMIENTO,
    ).to_crs(CRS_METRICO)

    return float(puntos.iloc[0].distance(puntos.iloc[1]))


def main():
    print("=" * 76)
    print("VERIFICACIÓN INDEPENDIENTE DE VENUES — geocoder Nominatim (OpenStreetMap)")
    print("=" * 76)

    if not RUTA_PLANILLA.exists():
        raise FileNotFoundError(f"Falta {RUTA_PLANILLA.name}. Corré antes scripts/03_verificar_venues.py")

    planilla = pd.read_csv(RUTA_PLANILLA, encoding="utf-8-sig")
    barrios, columna_de_barrio = cargar_barrios()

    ya_verificadas_a_mano = planilla["es_correcto"].notna() & (planilla["es_correcto"].astype(str).str.strip() != "")
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

        latitud_geocoder, longitud_geocoder = geocodificar_direccion_en_caba(str(fila["direccion_mas_comun"]))
        barrio_segun_geocoder = ubicar_punto_en_barrio(latitud_geocoder, longitud_geocoder, barrios, columna_de_barrio)
        distancia = medir_distancia_en_metros(
            fila["latitud_mediana"],
            fila["longitud_mediana"],
            latitud_geocoder,
            longitud_geocoder,
        )

        planilla.at[indice, "barrio_segun_geocoder"] = barrio_segun_geocoder
        planilla.at[indice, "metros_entre_geocoder_y_fuente"] = round(distancia) if distancia is not None else None
        planilla.at[indice, "metodo_de_verificacion"] = "geocoder_nominatim"

        coinciden = normalizar_texto_para_comparar(barrio_segun_geocoder) == normalizar_texto_para_comparar(fila["barrio_asignado"])

        planilla.at[indice, "es_correcto"] = "SI (geocoder)" if coinciden else "REVISAR"
        planilla.at[indice, "barrio_verificado_a_mano"] = ""

        marca = "  " if coinciden else " <"
        distancia_texto = f"{distancia:>6.0f}m" if distancia is not None else "   s/d"
        print(f"{fila['venue_normalizado'][:38]:<40} {str(fila['barrio_asignado'])[:16]:<18} {str(barrio_segun_geocoder)[:16]:<18} {distancia_texto}{marca}")

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
            print(f"    {fila['venue_normalizado'][:36]:<38} BA Data: {fila['barrio_asignado']:<18} OSM: {fila['barrio_segun_geocoder']}")
        print(
            "\n  Una discrepancia NO significa que BA Data esté mal: Nominatim\n"
            "  también se equivoca, sobre todo con esquinas y direcciones sin\n"
            "  altura. Es una señal de dónde mirar, no un veredicto."
        )

    print(f"\nEscrito: {RUTA_PLANILLA_COMPLETA.name}")
    print("=" * 76)


if __name__ == "__main__":
    main()
