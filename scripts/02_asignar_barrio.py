import sys
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import requests
from libpysal.weights import Queen
from sklearn.cluster import AgglomerativeClustering

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.normalizacion import normalizar_texto_para_comparar

URL_BARRIOS_GEOJSON = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/innovacion-transformacion-digital/barrios/barrios.geojson"

CABECERAS_HTTP = {"User-Agent": "musica-caba/1.0 (+https://github.com/francataldi/perfil-musical-caba)"}

CRS_ALMACENAMIENTO = "EPSG:4326"
CRS_METRICO = "EPSG:5347"

CANTIDAD_DE_BLOQUES_DE_CV = 5
MINIMO_DE_BARRIOS_POR_BLOQUE = 6

RAIZ_DEL_PROYECTO = Path(__file__).resolve().parent.parent
DIRECTORIO_CRUDO = RAIZ_DEL_PROYECTO / "data" / "raw"
DIRECTORIO_INTERMEDIO = RAIZ_DEL_PROYECTO / "data" / "interim"
DIRECTORIO_PROCESADO = RAIZ_DEL_PROYECTO / "data" / "processed"

RUTA_BARRIOS_LOCAL = DIRECTORIO_CRUDO / "barrios_caba.geojson"

NOMBRES_POSIBLES_DE_COLUMNA_BARRIO = ["BARRIO", "barrio", "nombre", "NOMBRE"]

ALIAS_DE_BARRIOS_DECLARADOS = {
    "BOCA": "LA BOCA",
    "MONTSERRAT": "MONSERRAT",
    "NUÑEZ": "NUNEZ",
}


def descargar_barrios_si_falta():
    if RUTA_BARRIOS_LOCAL.exists():
        print(f"Barrios ya en disco: {RUTA_BARRIOS_LOCAL.name}")
        return RUTA_BARRIOS_LOCAL

    print("Descargando el GeoJSON oficial de barrios...")
    DIRECTORIO_CRUDO.mkdir(parents=True, exist_ok=True)

    respuesta = requests.get(URL_BARRIOS_GEOJSON, headers=CABECERAS_HTTP, timeout=180)
    respuesta.raise_for_status()
    RUTA_BARRIOS_LOCAL.write_bytes(respuesta.content)

    print(f"Guardado: {RUTA_BARRIOS_LOCAL.name} ({len(respuesta.content) / 1e6:.1f} MB)")
    return RUTA_BARRIOS_LOCAL


def resolver_nombre_de_columna(dataframe, nombres_posibles):
    for nombre_candidato in nombres_posibles:
        if nombre_candidato in dataframe.columns:
            return nombre_candidato

    raise ValueError(f"Ninguna de estas columnas existe: {nombres_posibles}. Presentes: {sorted(dataframe.columns)}")


def cargar_y_verificar_barrios(ruta_geojson):
    barrios = gpd.read_file(ruta_geojson)

    columna_de_barrio = resolver_nombre_de_columna(barrios, NOMBRES_POSIBLES_DE_COLUMNA_BARRIO)

    print(f"  polígonos: {len(barrios)}")
    print(f"  CRS declarado: {barrios.crs}")
    print(f"  columna de nombre: '{columna_de_barrio}'")

    if len(barrios) != 48:
        print(f"  ATENCIÓN: se esperaban 48 barrios y hay {len(barrios)}. Puede ser otra versión del dataset.")

    if barrios.crs is None:
        print(f"  El archivo no declara CRS: se asume {CRS_ALMACENAMIENTO}")
        barrios = barrios.set_crs(CRS_ALMACENAMIENTO)

    barrios = barrios.to_crs(CRS_ALMACENAMIENTO)

    barrios["barrio_normalizado"] = barrios[columna_de_barrio].map(normalizar_texto_para_comparar)

    return barrios, columna_de_barrio


def cargar_eventos_mas_recientes():
    parquets_de_eventos = sorted(DIRECTORIO_CRUDO.glob("ba_data_actividades_*.parquet"))

    if not parquets_de_eventos:
        raise FileNotFoundError("No hay eventos en data/raw/. Corré primero scripts/01_descarga_ba_data.py")

    ruta_mas_reciente = parquets_de_eventos[-1]
    print(f"Leyendo eventos de {ruta_mas_reciente.name}")
    return pd.read_parquet(ruta_mas_reciente)


def convertir_eventos_a_geodataframe(eventos):
    eventos_con_coordenadas = eventos.dropna(subset=["venue_lat", "venue_lon"]).copy()

    cantidad_sin_coordenadas = len(eventos) - len(eventos_con_coordenadas)
    if cantidad_sin_coordenadas:
        print(f"  {cantidad_sin_coordenadas} eventos sin coordenadas quedan fuera ({cantidad_sin_coordenadas / len(eventos):.1%})")

    geometrias_de_puntos = gpd.points_from_xy(
        eventos_con_coordenadas["venue_lon"],
        eventos_con_coordenadas["venue_lat"],
    )

    return gpd.GeoDataFrame(
        eventos_con_coordenadas,
        geometry=geometrias_de_puntos,
        crs=CRS_ALMACENAMIENTO,
    )


def asignar_barrio_por_point_in_polygon(eventos_gdf, barrios_gdf, columna_de_barrio):
    if eventos_gdf.crs != barrios_gdf.crs:
        raise ValueError(f"CRS distintos: eventos={eventos_gdf.crs}, barrios={barrios_gdf.crs}. El sjoin daría resultados sin sentido.")

    columnas_de_barrios_a_pegar = barrios_gdf[[columna_de_barrio, "barrio_normalizado", "geometry"]].rename(columns={columna_de_barrio: "barrio"})

    eventos_con_barrio = gpd.sjoin(
        eventos_gdf,
        columnas_de_barrios_a_pegar,
        how="left",
        predicate="within",
    )

    cantidad_de_duplicados = eventos_con_barrio["id"].duplicated().sum()
    if cantidad_de_duplicados:
        print(f"  {cantidad_de_duplicados} eventos cayeron en más de un polígono (puntos sobre una frontera): se conserva el primero")
        eventos_con_barrio = eventos_con_barrio.drop_duplicates(subset=["id"])

    return eventos_con_barrio.drop(columns=["index_right"], errors="ignore")


def comparar_contra_barrio_declarado(eventos_con_barrio):
    if "barrio_declarado_por_la_fuente" not in eventos_con_barrio.columns:
        print("  La fuente no declara barrio: no hay control cruzado disponible.")
        return pd.DataFrame()

    comparables = eventos_con_barrio.dropna(subset=["barrio_normalizado", "barrio_declarado_por_la_fuente"]).copy()

    comparables["declarado_normalizado"] = (
        comparables["barrio_declarado_por_la_fuente"].map(normalizar_texto_para_comparar).replace(ALIAS_DE_BARRIOS_DECLARADOS)
    )

    coinciden = comparables["barrio_normalizado"] == comparables["declarado_normalizado"]

    print(f"\n  Control cruzado sobre {len(comparables)} eventos comparables:")
    print(f"    coinciden:  {coinciden.sum():>5} ({coinciden.mean():.1%})")
    print(f"    difieren:   {(~coinciden).sum():>5}")

    if coinciden.mean() < 0.90:
        print("    ATENCIÓN: menos del 90 % de acuerdo. Revisá CRS, nombres de barrio y versión del shapefile antes de seguir.")

    desacuerdos = comparables.loc[~coinciden, ["venue_nombre", "barrio_normalizado", "declarado_normalizado"]]

    if len(desacuerdos):
        print("\n    Top 10 desacuerdos (calculado -> declarado):")
        conteo_de_desacuerdos = desacuerdos.groupby(["barrio_normalizado", "declarado_normalizado"]).size().sort_values(ascending=False).head(10)
        for (calculado, declarado), cantidad in conteo_de_desacuerdos.items():
            print(f"      {cantidad:>4}  {calculado}  ->  {declarado}")

    return desacuerdos


def construir_matriz_de_contiguidad_queen(barrios_gdf, columna_de_barrio):
    pesos_queen = Queen.from_dataframe(barrios_gdf, ids=barrios_gdf[columna_de_barrio].tolist(), use_index=False)

    print(f"  vecinos promedio por barrio: {pesos_queen.mean_neighbors:.1f}")

    if pesos_queen.islands:
        print(f"  ATENCIÓN: {len(pesos_queen.islands)} barrios sin vecinos (islas): {pesos_queen.islands}")

    return pesos_queen


def definir_bloques_de_cv_espacial(barrios_gdf, columna_de_barrio, pesos_queen):
    barrios_en_metros = barrios_gdf.to_crs(CRS_METRICO)
    centroides = barrios_en_metros.geometry.centroid
    coordenadas_de_centroides = pd.DataFrame({"x": centroides.x, "y": centroides.y}).to_numpy()

    matriz_de_contiguidad = pesos_queen.sparse

    for cantidad_de_bloques in range(CANTIDAD_DE_BLOQUES_DE_CV, 2, -1):
        agrupamiento = AgglomerativeClustering(
            n_clusters=cantidad_de_bloques,
            connectivity=matriz_de_contiguidad,
            linkage="ward",
        )
        etiquetas_de_bloque = agrupamiento.fit_predict(coordenadas_de_centroides)
        tamanios_de_bloque = pd.Series(etiquetas_de_bloque).value_counts()

        if tamanios_de_bloque.min() >= MINIMO_DE_BARRIOS_POR_BLOQUE:
            break

        print(
            f"  con {cantidad_de_bloques} bloques el más chico tiene "
            f"{tamanios_de_bloque.min()} barrios (< {MINIMO_DE_BARRIOS_POR_BLOQUE}): "
            "se prueba con uno menos"
        )

    bloques = pd.DataFrame(
        {
            "barrio": barrios_gdf[columna_de_barrio].to_numpy(),
            "bloque_cv": etiquetas_de_bloque,
        }
    ).sort_values(["bloque_cv", "barrio"])

    print(f"  bloques finales: {cantidad_de_bloques}")
    print(f"  tamaños: {bloques['bloque_cv'].value_counts().sort_index().to_dict()}")

    return bloques


def dibujar_mapa_de_control(eventos_con_barrio, barrios_gdf, bloques, ruta_de_salida):
    figura, paneles = plt.subplots(1, 3, figsize=(21, 7))

    barrios_gdf.boundary.plot(ax=paneles[0], color="0.6", linewidth=0.5)
    eventos_con_barrio.plot(ax=paneles[0], markersize=2, alpha=0.25, color="crimson")
    paneles[0].set_title(f"Eventos geolocalizados (n={len(eventos_con_barrio)})\nbuscar puntos fuera de los polígonos")

    conteo_por_barrio = eventos_con_barrio.groupby("barrio_normalizado").size().rename("n_eventos")
    barrios_con_conteo = barrios_gdf.merge(conteo_por_barrio, left_on="barrio_normalizado", right_index=True, how="left")
    barrios_con_conteo["n_eventos"] = barrios_con_conteo["n_eventos"].fillna(0)
    barrios_con_conteo.plot(
        ax=paneles[1],
        column="n_eventos",
        cmap="YlOrRd",
        edgecolor="0.6",
        linewidth=0.4,
        legend=True,
    )
    paneles[1].set_title("Eventos por barrio\nrojo intenso = concentración")

    barrios_con_bloque = barrios_gdf.merge(bloques, left_on="barrio_normalizado", right_on="barrio", how="left")
    barrios_con_bloque.plot(
        ax=paneles[2],
        column="bloque_cv",
        cmap="tab10",
        edgecolor="white",
        linewidth=0.8,
        categorical=True,
        legend=True,
    )
    paneles[2].set_title("Bloques de CV espacial\ncada color debe ser una mancha contigua")

    for panel in paneles:
        panel.set_axis_off()

    figura.tight_layout()
    figura.savefig(ruta_de_salida, dpi=130, bbox_inches="tight")
    plt.close(figura)
    print(f"  mapa de control guardado en {ruta_de_salida.name}")


def main():
    print("=" * 66)
    print("ETAPA 2 — Geocodificación y asignación espacial")
    print("=" * 66)

    ruta_barrios = descargar_barrios_si_falta()

    print("\n[1/6] Cargando y verificando los polígonos de barrios")
    barrios, columna_de_barrio = cargar_y_verificar_barrios(ruta_barrios)

    print("\n[2/6] Cargando eventos de la Etapa 1")
    eventos = cargar_eventos_mas_recientes()
    eventos_gdf = convertir_eventos_a_geodataframe(eventos)

    print("\n[3/6] Spatial join point-in-polygon")
    eventos_con_barrio = asignar_barrio_por_point_in_polygon(eventos_gdf, barrios, columna_de_barrio)

    cantidad_sin_barrio = eventos_con_barrio["barrio"].isna().sum()
    cantidad_con_barrio = len(eventos_con_barrio) - cantidad_sin_barrio
    print(f"  dentro de CABA: {cantidad_con_barrio} ({cantidad_con_barrio / len(eventos_con_barrio):.1%})")
    print(f"  fuera de CABA:  {cantidad_sin_barrio} (esperable: GBA)")

    print("\n[4/6] Control cruzado contra el barrio declarado por la fuente")
    comparar_contra_barrio_declarado(eventos_con_barrio)

    print("\n[5/6] Matriz de contigüidad queen y bloques de CV espacial")
    pesos_queen = construir_matriz_de_contiguidad_queen(barrios, columna_de_barrio)
    bloques = definir_bloques_de_cv_espacial(barrios, columna_de_barrio, pesos_queen)

    DIRECTORIO_PROCESADO.mkdir(parents=True, exist_ok=True)
    ruta_bloques = DIRECTORIO_PROCESADO / "bloques_cv.csv"
    bloques_para_guardar = bloques.copy()
    bloques_para_guardar["barrio"] = bloques_para_guardar["barrio"].map(normalizar_texto_para_comparar)
    bloques_para_guardar.to_csv(ruta_bloques, index=False)
    print(f"  bloques persistidos en {ruta_bloques.name}")

    print("\n[6/6] Mapa de control")
    DIRECTORIO_INTERMEDIO.mkdir(parents=True, exist_ok=True)
    dibujar_mapa_de_control(
        eventos_con_barrio.dropna(subset=["barrio"]),
        barrios,
        bloques_para_guardar,
        DIRECTORIO_INTERMEDIO / "mapa_de_control.png",
    )

    eventos_dentro_de_caba = eventos_con_barrio.dropna(subset=["barrio"]).drop(columns=["geometry"])
    ruta_salida = DIRECTORIO_INTERMEDIO / "eventos_geolocalizados.parquet"
    eventos_dentro_de_caba.to_parquet(ruta_salida, index=False)

    eventos_del_panel = eventos_dentro_de_caba[~eventos_dentro_de_caba["fecha"].dt.year.isin([2020, 2021])]

    print(f"\n{'=' * 66}")
    print("GATE DE LA ETAPA 2")
    print(f"  geocodificados:     {cantidad_con_barrio / len(eventos):.1%}  (>= 85 %)")
    print(f"  barrios con evento: {eventos_del_panel['barrio'].nunique()}  (>= 40)")
    print(f"  eventos del panel:  {len(eventos_del_panel)}  (>= 3000)")
    print(f"\nEscrito: {ruta_salida.name}")
    print(f"{'=' * 66}")


if __name__ == "__main__":
    main()
