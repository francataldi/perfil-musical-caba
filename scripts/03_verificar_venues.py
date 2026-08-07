"""
Prepara la verificación manual de los venues con más eventos.

Por qué existe este paso
------------------------
Los venues más frecuentes concentran la mayor parte de la señal del proyecto:
un error en el barrio asignado a uno solo de ellos desplaza cientos de eventos
y contamina todas las conclusiones posteriores. Verificarlos es tedioso y es
innegociable.

Este script NO reemplaza la verificación manual: la dirige. Produce tres
diagnósticos que señalan dónde mirar, y una tabla para revisar a ojo.

Diagnósticos
------------
1. DISPERSIÓN DE COORDENADAS por venue. Si los eventos de "Usina del Arte"
   están repartidos en 3 km, o el nombre agrupa lugares distintos o la fuente
   tiene coordenadas corruptas. Se mide en METROS, reproyectando a EPSG:5347.
2. VENUES EN MÁS DE UN BARRIO. Un lugar físico está en un solo barrio. Si
   aparece en dos, o las coordenadas están mal o el nombre es ambiguo.
3. NOMBRES CASI IGUALES. "CC Recoleta" y "Centro Cultural Recoleta" son el
   mismo lugar contado dos veces, lo que parte la señal de un barrio en dos.

Salida
------
    data/interim/verificacion_venues.csv  — para completar a mano

Uso:
    conda activate musica-caba
    python scripts/03_verificar_venues.py
"""

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.normalizacion import normalizar_texto_para_comparar  # noqa: E402

CRS_ALMACENAMIENTO = "EPSG:4326"
CRS_METRICO = "EPSG:5347"

CANTIDAD_DE_VENUES_A_VERIFICAR = 30
METROS_DE_DISPERSION_ACEPTABLE = 300
# Se bajó de 88 a 80 el 2026-08-05: con 88 se escapaban duplicados reales que
# se veían a ojo en el top 30, como "CENTRO CULTURAL SAN MARTIN" vs "CENTRO
# CULTURAL GENERAL SAN MARTIN" (una palabra de diferencia sobre 34 caracteres
# baja el puntaje a ~86). Un umbral alto no es "más seguro": produce falsos
# negativos silenciosos, que es peor que revisar de más a mano.
UMBRAL_DE_SIMILITUD_DE_NOMBRES = 80

RAIZ_DEL_PROYECTO = Path(__file__).resolve().parent.parent
DIRECTORIO_INTERMEDIO = RAIZ_DEL_PROYECTO / "data" / "interim"


def cargar_eventos_geolocalizados():
    """
    Carga el parquet producido por la Etapa 2.

    Devuelve
    --------
    DataFrame con barrio asignado.
    """
    ruta = DIRECTORIO_INTERMEDIO / "eventos_geolocalizados.parquet"

    if not ruta.exists():
        raise FileNotFoundError(
            "Falta data/interim/eventos_geolocalizados.parquet. "
            "Corré primero scripts/02_asignar_barrio.py"
        )

    return pd.read_parquet(ruta)


def resumir_venues_por_frecuencia(eventos):
    """
    Agrupa los eventos por nombre de venue normalizado y los ordena por volumen.

    Objetivo
    --------
    Identificar dónde está concentrada la señal. Si 30 venues explican el 60 %
    de los eventos, verificar esos 30 cubre el 60 % del riesgo de error, y es
    una tarde de trabajo en lugar de un mes.

    El agrupamiento se hace sobre el nombre NORMALIZADO (sin tildes, en
    mayúsculas, sin espacios repetidos) porque "Usina del Arte", "USINA DEL
    ARTE" y "Usina  del Arte" son el mismo lugar y contarlos por separado
    subestimaría la concentración.

    Inputs
    ------
    eventos : DataFrame con venue_nombre, barrio, venue_lat, venue_lon.

    Devuelve
    --------
    DataFrame ordenado por cantidad de eventos, descendente.
    """
    eventos = eventos.copy()
    eventos["venue_normalizado"] = eventos["venue_nombre"].map(
        normalizar_texto_para_comparar
    )

    resumen = (
        eventos.groupby("venue_normalizado")
        .agg(
            n_eventos=("id", "size"),
            barrios_asignados=("barrio", lambda serie: sorted(set(serie.dropna()))),
            n_barrios=("barrio", lambda serie: serie.dropna().nunique()),
            direccion_mas_comun=(
                "venue_direccion",
                lambda serie: serie.mode().iat[0] if not serie.mode().empty else "",
            ),
            latitud_mediana=("venue_lat", "median"),
            longitud_mediana=("venue_lon", "median"),
            primera_fecha=("fecha", "min"),
            ultima_fecha=("fecha", "max"),
        )
        .sort_values("n_eventos", ascending=False)
    )

    return resumen


def medir_dispersion_de_coordenadas_en_metros(eventos):
    """
    Calcula, para cada venue, cuán dispersos están sus puntos, en metros.

    Objetivo
    --------
    Detectar venues cuyo nombre agrupa ubicaciones distintas, o cuyas
    coordenadas están corruptas en la fuente. Un lugar físico tiene una sola
    posición: si sus eventos aparecen repartidos en kilómetros, hay un problema.

    Por qué se reproyecta a EPSG:5347
    ---------------------------------
    Este es el caso donde el CRS métrico es obligatorio. La dispersión es una
    DISTANCIA, y en EPSG:4326 las coordenadas están en grados: un grado de
    latitud mide ~111 km pero uno de longitud mide ~92 km a la altura de Buenos
    Aires, así que un desvío estándar calculado en grados mezcla dos unidades
    distintas y no se puede comparar contra un umbral en metros.

    Se usa la distancia al centroide del venue y se reporta el máximo, que es
    más interpretable que un desvío estándar: responde "¿cuán lejos está el
    punto más alejado del centro?".

    Inputs
    ------
    eventos : DataFrame con venue_nombre, venue_lat, venue_lon.

    Devuelve
    --------
    Series indexada por venue_normalizado, con la dispersión máxima en metros.
    """
    eventos = eventos.dropna(subset=["venue_lat", "venue_lon"]).copy()
    eventos["venue_normalizado"] = eventos["venue_nombre"].map(
        normalizar_texto_para_comparar
    )

    puntos = gpd.GeoDataFrame(
        eventos,
        geometry=gpd.points_from_xy(eventos["venue_lon"], eventos["venue_lat"]),
        crs=CRS_ALMACENAMIENTO,
    ).to_crs(CRS_METRICO)

    puntos["x_metros"] = puntos.geometry.x
    puntos["y_metros"] = puntos.geometry.y

    centros_por_venue = puntos.groupby("venue_normalizado")[
        ["x_metros", "y_metros"]
    ].transform("mean")

    distancias_al_centro = (
        (puntos["x_metros"] - centros_por_venue["x_metros"]) ** 2
        + (puntos["y_metros"] - centros_por_venue["y_metros"]) ** 2
    ) ** 0.5

    puntos["distancia_al_centro_del_venue"] = distancias_al_centro

    return puntos.groupby("venue_normalizado")[
        "distancia_al_centro_del_venue"
    ].max()


def detectar_nombres_casi_iguales(nombres_de_venues):
    """
    Busca pares de nombres de venue que probablemente sean el mismo lugar.

    Objetivo
    --------
    Un mismo venue escrito de dos formas parte su señal en dos filas y
    subestima la concentración de un barrio. "CENTRO CULTURAL RECOLETA" y
    "CC RECOLETA" tienen que colapsar.

    Se usa rapidfuzz con token_sort_ratio, que compara conjuntos de palabras
    ignorando el orden: "TEATRO COLON" y "COLON TEATRO" dan 100. Es lo
    adecuado para nombres de lugares, donde el orden varía.

    El umbral se calibró contra el resultado real: con 88 se escapaban
    duplicados que se veían a simple vista en la lista del top 30. Esta función
    NO decide fusiones: solo señala candidatos para que los mire una persona.
    Por eso conviene un umbral permisivo — un falso positivo cuesta diez
    segundos de lectura, un falso negativo se cuela en el análisis final.

    Inputs
    ------
    nombres_de_venues : list[str] normalizados.

    Devuelve
    --------
    DataFrame con los pares candidatos y su puntaje de similitud.
    """
    # Se comparan los nombres de dos formas complementarias porque cada scorer
    # falla en un caso distinto:
    #   - token_sort_ratio parte por espacios y compara conjuntos de palabras,
    #     así que tolera el orden distinto pero SE ROMPE si falta un espacio:
    #     "BUENOSAYRES" no se parece a los tokens "BUENOS" ni "AIRES".
    #   - ratio sobre el nombre sin espacios ignora la tokenización y detecta
    #     justamente ese caso, pero es sensible al orden de las palabras.
    nombres_sin_espacios = [nombre.replace(" ", "") for nombre in nombres_de_venues]
    puntajes_maximos_por_par = {}

    for indice, nombre_actual in enumerate(nombres_de_venues):
        for indice_siguiente in range(indice + 1, len(nombres_de_venues)):
            nombre_comparado = nombres_de_venues[indice_siguiente]

            puntaje_por_tokens = fuzz.token_sort_ratio(nombre_actual, nombre_comparado)
            puntaje_sin_espacios = fuzz.ratio(
                nombres_sin_espacios[indice], nombres_sin_espacios[indice_siguiente]
            )
            mejor_puntaje = max(puntaje_por_tokens, puntaje_sin_espacios)

            if mejor_puntaje >= UMBRAL_DE_SIMILITUD_DE_NOMBRES:
                puntajes_maximos_por_par[(nombre_actual, nombre_comparado)] = (
                    mejor_puntaje
                )

    pares_candidatos = [
        {"venue_a": venue_a, "venue_b": venue_b, "similitud": round(puntaje, 1)}
        for (venue_a, venue_b), puntaje in puntajes_maximos_por_par.items()
    ]

    if not pares_candidatos:
        return pd.DataFrame(columns=["venue_a", "venue_b", "similitud"])

    return pd.DataFrame(pares_candidatos).sort_values("similitud", ascending=False)


def main():
    """Orquesta los diagnósticos y escribe la planilla de verificación manual."""
    print("=" * 74)
    print("VERIFICACIÓN DE VENUES — preparación para la revisión manual")
    print("=" * 74)

    eventos = cargar_eventos_geolocalizados()
    resumen = resumir_venues_por_frecuencia(eventos)
    dispersion = medir_dispersion_de_coordenadas_en_metros(eventos)
    resumen["dispersion_maxima_metros"] = dispersion.reindex(resumen.index).round(0)

    top_venues = resumen.head(CANTIDAD_DE_VENUES_A_VERIFICAR)
    cobertura = top_venues["n_eventos"].sum() / len(eventos)

    print(
        f"\nLos {CANTIDAD_DE_VENUES_A_VERIFICAR} venues más frecuentes concentran "
        f"{top_venues['n_eventos'].sum()} de {len(eventos)} eventos ({cobertura:.1%}).\n"
    )

    print("-" * 74)
    print("TOP 30 VENUES")
    print("-" * 74)
    print(f"{'#':>3} {'EVENTOS':>8}  {'BARRIO':<22} {'DISPERS.':>9}  VENUE")
    for posicion, (nombre_del_venue, fila) in enumerate(top_venues.iterrows(), start=1):
        barrio_asignado = (
            fila["barrios_asignados"][0] if fila["barrios_asignados"] else "SIN BARRIO"
        )
        marca_de_alerta = (
            " !" if fila["dispersion_maxima_metros"] > METROS_DE_DISPERSION_ACEPTABLE
            else "  "
        )
        print(
            f"{posicion:>3} {fila['n_eventos']:>8}  {barrio_asignado[:22]:<22} "
            f"{fila['dispersion_maxima_metros']:>8.0f}m{marca_de_alerta} "
            f"{nombre_del_venue[:34]}"
        )

    # ── Diagnóstico 1: dispersión de coordenadas ──────────────────────────────
    print("\n" + "-" * 74)
    print("DIAGNÓSTICO 1 — venues con coordenadas dispersas")
    print("-" * 74)
    dispersos = top_venues[
        top_venues["dispersion_maxima_metros"] > METROS_DE_DISPERSION_ACEPTABLE
    ]
    if dispersos.empty:
        print(f"  Ninguno supera los {METROS_DE_DISPERSION_ACEPTABLE} m. Bien.")
    else:
        print(
            f"  {len(dispersos)} venues con puntos a más de "
            f"{METROS_DE_DISPERSION_ACEPTABLE} m de su propio centro:"
        )
        for nombre_del_venue, fila in dispersos.iterrows():
            print(
                f"    {fila['dispersion_maxima_metros']:>7.0f} m  "
                f"({fila['n_eventos']:>4} eventos)  {nombre_del_venue}"
            )
        print(
            "\n  Qué significa: o el nombre agrupa lugares distintos (un festival\n"
            "  itinerante, una institución con varias sedes), o la fuente tiene\n"
            "  coordenadas corruptas. Hay que mirar caso por caso."
        )

    # ── Diagnóstico 2: venues en más de un barrio ─────────────────────────────
    print("\n" + "-" * 74)
    print("DIAGNÓSTICO 2 — venues asignados a más de un barrio")
    print("-" * 74)
    en_varios_barrios = top_venues[top_venues["n_barrios"] > 1]
    if en_varios_barrios.empty:
        print("  Ninguno. Cada venue del top 30 cae en un solo barrio.")
    else:
        for nombre_del_venue, fila in en_varios_barrios.iterrows():
            print(
                f"    {nombre_del_venue[:40]:<42} -> "
                f"{', '.join(fila['barrios_asignados'])}"
            )
        print(
            "\n  Un lugar físico está en un solo barrio. Si aparece en dos, o las\n"
            "  coordenadas varían, o el nombre agrupa sedes distintas."
        )

    # ── Diagnóstico 3: nombres casi iguales ───────────────────────────────────
    print("\n" + "-" * 74)
    print("DIAGNÓSTICO 3 — nombres casi iguales (posible mismo venue)")
    print("-" * 74)
    nombres_frecuentes = resumen.head(150).index.tolist()
    pares_similares = detectar_nombres_casi_iguales(nombres_frecuentes)
    if pares_similares.empty:
        print("  No se detectaron pares por encima del umbral.")
    else:
        print(f"  {len(pares_similares)} pares con similitud >= "
              f"{UMBRAL_DE_SIMILITUD_DE_NOMBRES}:")
        for _, fila in pares_similares.head(15).iterrows():
            print(
                f"    {fila['similitud']:>5.1f}  {fila['venue_a'][:32]:<34}"
                f"  ~  {fila['venue_b'][:32]}"
            )
        print(
            "\n  Si dos de estos son el mismo lugar, su señal está partida en dos\n"
            "  filas y la concentración del barrio queda subestimada."
        )

    # ── Planilla para completar a mano ────────────────────────────────────────
    planilla = top_venues.reset_index()[
        [
            "venue_normalizado",
            "n_eventos",
            "direccion_mas_comun",
            "barrios_asignados",
            "latitud_mediana",
            "longitud_mediana",
            "dispersion_maxima_metros",
            "primera_fecha",
            "ultima_fecha",
        ]
    ].copy()

    planilla["barrio_asignado"] = planilla["barrios_asignados"].map(
        lambda lista: lista[0] if lista else ""
    )
    planilla = planilla.drop(columns=["barrios_asignados"])

    # Columnas vacías que Franco completa a mano mirando cada venue.
    planilla["barrio_verificado_a_mano"] = ""
    planilla["es_correcto"] = ""
    planilla["observaciones"] = ""
    planilla["link_para_verificar"] = (
        "https://www.google.com/maps/search/?api=1&query="
        + planilla["latitud_mediana"].round(6).astype(str)
        + ","
        + planilla["longitud_mediana"].round(6).astype(str)
    )

    ruta_planilla = DIRECTORIO_INTERMEDIO / "verificacion_venues.csv"
    planilla.to_csv(ruta_planilla, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 74)
    print(f"Planilla escrita: {ruta_planilla}")
    print(
        "\nCómo completarla:\n"
        "  1. Abrí el CSV. Cada fila tiene un 'link_para_verificar' que abre\n"
        "     Google Maps en las coordenadas medianas de ese venue.\n"
        "  2. Confirmá que el lugar existe ahí y anotá en qué barrio está.\n"
        "  3. Completá 'barrio_verificado_a_mano' y 'es_correcto' (SI/NO).\n"
        "  4. Prestá atención especial a los que tienen la marca ! de dispersión."
    )
    print("=" * 74)


if __name__ == "__main__":
    main()
