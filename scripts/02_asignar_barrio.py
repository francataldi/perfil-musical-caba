"""
Asigna a cada evento el barrio de CABA que lo contiene, y prepara la estructura
espacial que van a usar las etapas siguientes.

Produce tres artefactos:
  1. data/interim/eventos_geolocalizados.parquet  — eventos con barrio asignado
  2. data/processed/bloques_cv.csv                — los 5 bloques de CV espacial
  3. data/interim/mapa_de_control.png             — el QA visual, innegociable

CRS: se almacena en EPSG:4326 (lat/lon, grados) y se reproyecta a EPSG:5347
(POSGAR 2007 Faja 5, metros) para todo cálculo métrico. El point-in-polygon NO
necesita reproyección porque adentro/afuera es topología, no geometría métrica;
los centroides que alimentan el clustering de bloques SÍ la necesitan.

Uso:
    conda activate musica-caba
    python scripts/02_asignar_barrio.py
"""

import sys
from pathlib import Path

import geopandas as gpd
import matplotlib

# Backend sin ventana: el script corre desde terminal y solo guarda un PNG.
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402
from libpysal.weights import Queen  # noqa: E402
from sklearn.cluster import AgglomerativeClustering  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.normalizacion import normalizar_texto_para_comparar  # noqa: E402

URL_BARRIOS_GEOJSON = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "innovacion-transformacion-digital/barrios/barrios.geojson"
)

CABECERAS_HTTP = {
    "User-Agent": "musica-caba/1.0 (+https://github.com/francataldi/perfil-musical-caba)"
}

CRS_ALMACENAMIENTO = "EPSG:4326"  # lat/lon en grados, lo que devuelve el GPS
CRS_METRICO = "EPSG:5347"  # POSGAR 2007 Faja 5, en metros

CANTIDAD_DE_BLOQUES_DE_CV = 5
MINIMO_DE_BARRIOS_POR_BLOQUE = 6

RAIZ_DEL_PROYECTO = Path(__file__).resolve().parent.parent
DIRECTORIO_CRUDO = RAIZ_DEL_PROYECTO / "data" / "raw"
DIRECTORIO_INTERMEDIO = RAIZ_DEL_PROYECTO / "data" / "interim"
DIRECTORIO_PROCESADO = RAIZ_DEL_PROYECTO / "data" / "processed"

RUTA_BARRIOS_LOCAL = DIRECTORIO_CRUDO / "barrios_caba.geojson"

# Nombres posibles de la columna que tiene el nombre del barrio. El GCBA cambió
# la convención entre versiones del dataset.
NOMBRES_POSIBLES_DE_COLUMNA_BARRIO = ["BARRIO", "barrio", "nombre", "NOMBRE"]

# El GCBA escribe algunos barrios distinto en el shapefile y en sus propios CSV
# de actividades. Son el mismo barrio, no un desacuerdo geográfico. Este mapa
# se usa SOLO para el control cruzado; el nombre canónico del proyecto es
# siempre el del shapefile oficial.
ALIAS_DE_BARRIOS_DECLARADOS = {
    "BOCA": "LA BOCA",
    "MONTSERRAT": "MONSERRAT",
    "NUÑEZ": "NUNEZ",
}


def descargar_barrios_si_falta():
    """
    Descarga el GeoJSON oficial de barrios de CABA, si no está ya en disco.

    Objetivo
    --------
    Persistir el crudo una sola vez. Volver a descargarlo en cada corrida sería
    lento y pondría el resultado a merced de que el GCBA cambie el archivo entre
    ejecuciones: dos corridas del mismo análisis podrían dar distinto.

    Se usa GeoJSON y no el shapefile (.zip) porque un shapefile son cuatro
    archivos que tienen que viajar juntos (.shp con la geometría, .dbf con los
    atributos, .shx con el índice, .prj con el CRS) y perder el .prj significa
    perder el sistema de coordenadas.

    Devuelve
    --------
    Path al archivo local.
    """
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
    """
    Busca cuál de varios nombres alternativos existe en el DataFrame.

    Objetivo
    --------
    Absorber los cambios de convención del GCBA entre versiones del dataset sin
    que el resto del código tenga que saber cuál está vigente.

    Inputs
    ------
    dataframe : DataFrame o GeoDataFrame
    nombres_posibles : list[str], en orden de preferencia

    Devuelve
    --------
    str con el nombre encontrado.

    Raises
    ------
    ValueError si ninguno está presente.
    """
    for nombre_candidato in nombres_posibles:
        if nombre_candidato in dataframe.columns:
            return nombre_candidato

    raise ValueError(
        f"Ninguna de estas columnas existe: {nombres_posibles}. "
        f"Presentes: {sorted(dataframe.columns)}"
    )


def cargar_y_verificar_barrios(ruta_geojson):
    """
    Carga los polígonos de barrios y verifica que sean lo que se espera.

    Objetivo
    --------
    No confiar a ciegas en un archivo descargado. Antes de hacer el join hay que
    saber cuántos polígonos hay, en qué CRS vienen y cómo se llama la columna
    del nombre. Un shapefile con 47 o 52 polígonos en vez de 48 significa que es
    otra versión del dataset y los resultados no serían comparables.

    Inputs
    ------
    ruta_geojson : Path

    Devuelve
    --------
    tuple (GeoDataFrame en CRS_ALMACENAMIENTO, nombre_de_la_columna_de_barrio)
    """
    barrios = gpd.read_file(ruta_geojson)

    columna_de_barrio = resolver_nombre_de_columna(
        barrios, NOMBRES_POSIBLES_DE_COLUMNA_BARRIO
    )

    print(f"  polígonos: {len(barrios)}")
    print(f"  CRS declarado: {barrios.crs}")
    print(f"  columna de nombre: '{columna_de_barrio}'")

    if len(barrios) != 48:
        print(
            f"  ATENCIÓN: se esperaban 48 barrios y hay {len(barrios)}. "
            "Puede ser otra versión del dataset."
        )

    # Si el archivo no declara CRS hay que asumirlo; los GeoJSON del GCBA vienen
    # en WGS84. Asumir mal acá desplaza todos los puntos y el join da vacío.
    if barrios.crs is None:
        print(f"  El archivo no declara CRS: se asume {CRS_ALMACENAMIENTO}")
        barrios = barrios.set_crs(CRS_ALMACENAMIENTO)

    # to_crs REPROYECTA (convierte coordenadas); set_crs solo ETIQUETA sin tocar
    # los números. Confundirlas es el error espacial más caro que existe.
    barrios = barrios.to_crs(CRS_ALMACENAMIENTO)

    barrios["barrio_normalizado"] = barrios[columna_de_barrio].map(
        normalizar_texto_para_comparar
    )

    return barrios, columna_de_barrio


def cargar_eventos_mas_recientes():
    """
    Carga el parquet de eventos más reciente producido por la Etapa 1.

    Objetivo
    --------
    No hardcodear la fecha del archivo. Si se re-descarga BA Data mañana, este
    script toma el nuevo sin tocar código.

    Devuelve
    --------
    DataFrame de eventos.
    """
    parquets_de_eventos = sorted(DIRECTORIO_CRUDO.glob("ba_data_actividades_*.parquet"))

    if not parquets_de_eventos:
        raise FileNotFoundError(
            "No hay eventos en data/raw/. Corré primero "
            "scripts/01_descarga_ba_data.py"
        )

    ruta_mas_reciente = parquets_de_eventos[-1]
    print(f"Leyendo eventos de {ruta_mas_reciente.name}")
    return pd.read_parquet(ruta_mas_reciente)


def convertir_eventos_a_geodataframe(eventos):
    """
    Convierte el DataFrame de eventos en un GeoDataFrame de puntos.

    Objetivo
    --------
    Un DataFrame con dos columnas numéricas no es un objeto espacial: pandas no
    sabe que 'venue_lat' y 'venue_lon' son coordenadas. El GeoDataFrame agrega
    una columna 'geometry' con objetos Point y un CRS asociado, que es lo que
    habilita el spatial join.

    OJO con el orden de los argumentos: points_from_xy(x, y) espera
    x = LONGITUD e y = LATITUD, en ese orden. Es al revés de como se dicen las
    coordenadas en el habla común ("latitud, longitud"), y es la causa número
    uno de puntos que aparecen en el océano Índico.

    Inputs
    ------
    eventos : DataFrame con columnas venue_lat y venue_lon.

    Devuelve
    --------
    GeoDataFrame en CRS_ALMACENAMIENTO, solo con las filas que tenían coordenadas.
    """
    eventos_con_coordenadas = eventos.dropna(subset=["venue_lat", "venue_lon"]).copy()

    cantidad_sin_coordenadas = len(eventos) - len(eventos_con_coordenadas)
    if cantidad_sin_coordenadas:
        print(
            f"  {cantidad_sin_coordenadas} eventos sin coordenadas quedan fuera "
            f"({cantidad_sin_coordenadas / len(eventos):.1%})"
        )

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
    """
    Asigna a cada evento el barrio cuyo polígono lo contiene.

    Objetivo
    --------
    Convertir un par de coordenadas en la unidad de análisis del proyecto. Es el
    paso que hace existir al panel barrio × trimestre.

    Por qué NO se reproyecta a EPSG:5347 acá
    ----------------------------------------
    "Estar contenido en" es una relación TOPOLÓGICA: no cambia con la
    proyección. Un punto adentro de un polígono sigue adentro en cualquier CRS.
    Reproyectar sería trabajo inútil. La reproyección a metros hace falta para
    distancias, áreas y centroides — que es justo lo que necesita el clustering
    de bloques, más abajo.

    Lo que SÍ es obligatorio: que ambas capas estén en el MISMO CRS. GeoPandas
    a veces avisa y a veces no.

    Inputs
    ------
    eventos_gdf : GeoDataFrame de puntos
    barrios_gdf : GeoDataFrame de polígonos
    columna_de_barrio : str

    Devuelve
    --------
    GeoDataFrame de eventos con las columnas 'barrio' y 'barrio_normalizado'.
    Los eventos fuera de CABA quedan con barrio nulo, no se descartan acá.
    """
    if eventos_gdf.crs != barrios_gdf.crs:
        raise ValueError(
            f"CRS distintos: eventos={eventos_gdf.crs}, barrios={barrios_gdf.crs}. "
            "El sjoin daría resultados sin sentido."
        )

    columnas_de_barrios_a_pegar = barrios_gdf[
        [columna_de_barrio, "barrio_normalizado", "geometry"]
    ].rename(columns={columna_de_barrio: "barrio"})

    # how="left" conserva TODOS los eventos, incluso los que no caen en ningún
    # polígono. Con how="inner" desaparecerían en silencio y no se podría
    # reportar cuántos quedaron afuera, que es justamente el dato de control.
    eventos_con_barrio = gpd.sjoin(
        eventos_gdf,
        columnas_de_barrios_a_pegar,
        how="left",
        predicate="within",
    )

    # Un punto exactamente sobre una frontera puede matchear dos polígonos y
    # duplicar la fila. Es raro pero rompe los conteos del panel si pasa.
    cantidad_de_duplicados = eventos_con_barrio["id"].duplicated().sum()
    if cantidad_de_duplicados:
        print(
            f"  {cantidad_de_duplicados} eventos cayeron en más de un polígono "
            "(puntos sobre una frontera): se conserva el primero"
        )
        eventos_con_barrio = eventos_con_barrio.drop_duplicates(subset=["id"])

    return eventos_con_barrio.drop(columns=["index_right"], errors="ignore")


def comparar_contra_barrio_declarado(eventos_con_barrio):
    """
    Compara el barrio calculado con el que declara la fuente.

    Objetivo
    --------
    Validar el spatial join contra una referencia externa. Es la única
    verificación disponible que no depende del propio código: si el 95 % de los
    eventos cae en el barrio que el GCBA dice, el join está bien Y el shapefile
    es el correcto. Si coincide el 60 %, hay un problema de CRS, de nombres o de
    versión del shapefile. Si coincide el 0 %, lat y lon están invertidas.

    Es diagnóstico, no un número decorativo: la magnitud del desacuerdo señala
    qué tipo de error buscar.

    Inputs
    ------
    eventos_con_barrio : GeoDataFrame con 'barrio_normalizado' y
        'barrio_declarado_por_la_fuente'.

    Devuelve
    --------
    DataFrame con los casos en desacuerdo, para inspección manual.
    """
    if "barrio_declarado_por_la_fuente" not in eventos_con_barrio.columns:
        print("  La fuente no declara barrio: no hay control cruzado disponible.")
        return pd.DataFrame()

    comparables = eventos_con_barrio.dropna(
        subset=["barrio_normalizado", "barrio_declarado_por_la_fuente"]
    ).copy()

    # Se normaliza y además se aplican los alias: el GCBA escribe "BOCA" en sus
    # CSV y "LA BOCA" en el shapefile. Sin esto, 1.309 eventos figuran como
    # desacuerdo cuando en realidad el punto cayó en el barrio correcto.
    comparables["declarado_normalizado"] = (
        comparables["barrio_declarado_por_la_fuente"]
        .map(normalizar_texto_para_comparar)
        .replace(ALIAS_DE_BARRIOS_DECLARADOS)
    )

    coinciden = (
        comparables["barrio_normalizado"] == comparables["declarado_normalizado"]
    )

    print(f"\n  Control cruzado sobre {len(comparables)} eventos comparables:")
    print(f"    coinciden:  {coinciden.sum():>5} ({coinciden.mean():.1%})")
    print(f"    difieren:   {(~coinciden).sum():>5}")

    if coinciden.mean() < 0.90:
        print(
            "    ATENCIÓN: menos del 90 % de acuerdo. Revisá CRS, nombres de "
            "barrio y versión del shapefile antes de seguir."
        )

    desacuerdos = comparables.loc[
        ~coinciden, ["venue_nombre", "barrio_normalizado", "declarado_normalizado"]
    ]

    if len(desacuerdos):
        print("\n    Top 10 desacuerdos (calculado -> declarado):")
        conteo_de_desacuerdos = (
            desacuerdos.groupby(["barrio_normalizado", "declarado_normalizado"])
            .size()
            .sort_values(ascending=False)
            .head(10)
        )
        for (calculado, declarado), cantidad in conteo_de_desacuerdos.items():
            print(f"      {cantidad:>4}  {calculado}  ->  {declarado}")

    return desacuerdos


def construir_matriz_de_contiguidad_queen(barrios_gdf, columna_de_barrio):
    """
    Construye la matriz de pesos espaciales por contigüidad tipo queen.

    Objetivo
    --------
    Codificar qué barrios son vecinos. Se usa dos veces en el proyecto:
    para restringir el clustering de bloques de CV (que ningún bloque salga
    partido en dos pedazos del mapa) y para la I de Moran sobre residuos en la
    Etapa 7. Se calcula una sola vez, acá.

    Queen vs. rook
    --------------
    La analogía viene del ajedrez. Contigüidad ROOK: dos polígonos son vecinos
    si comparten un BORDE (una arista completa), como se mueve la torre.
    Contigüidad QUEEN: alcanza con compartir un solo PUNTO, como se mueve la
    reina. Queen es más inclusiva y es la convención en análisis urbano, donde
    tres barrios suelen tocarse en una esquina.

    No requiere reproyección: la contigüidad también es topología.

    Inputs
    ------
    barrios_gdf : GeoDataFrame de polígonos
    columna_de_barrio : str

    Devuelve
    --------
    libpysal.weights.Queen
    """
    pesos_queen = Queen.from_dataframe(
        barrios_gdf, ids=barrios_gdf[columna_de_barrio].tolist(), use_index=False
    )

    print(f"  vecinos promedio por barrio: {pesos_queen.mean_neighbors:.1f}")

    if pesos_queen.islands:
        print(
            f"  ATENCIÓN: {len(pesos_queen.islands)} barrios sin vecinos "
            f"(islas): {pesos_queen.islands}"
        )

    return pesos_queen


def definir_bloques_de_cv_espacial(barrios_gdf, columna_de_barrio, pesos_queen):
    """
    Parte los 48 barrios en bloques geográficamente contiguos para la CV espacial.

    Objetivo
    --------
    Implementar el esquema de validación congelado en docs/00_protocolo.md § 6.
    Cada fold de la validación cruzada deja un bloque entero afuera, con todos
    sus trimestres. Es el análogo espacial del walk-forward temporal: evita que
    el modelo vea barrios vecinos del set de test durante el entrenamiento y
    sobrestime su capacidad de generalizar.

    Por qué SÍ se reproyecta acá
    ----------------------------
    El clustering agrupa por DISTANCIA entre centroides. En EPSG:4326 esa
    distancia estaría en grados, y un grado de longitud en Buenos Aires mide
    ~92 km mientras que uno de latitud mide ~111 km: la métrica estaría
    deformada en un 20 % en una dirección. En EPSG:5347 las coordenadas están
    en metros y la distancia euclídea es la distancia real.

    El parámetro connectivity
    -------------------------
    Sin él, AgglomerativeClustering puede armar un bloque con barrios que no se
    tocan, lo cual arruina el propósito: dos pedazos separados del mapa en el
    mismo fold no aíslan la autocorrelación espacial. Pasarle la matriz queen
    fuerza que solo se puedan fusionar grupos contiguos.

    Inputs
    ------
    barrios_gdf : GeoDataFrame
    columna_de_barrio : str
    pesos_queen : libpysal.weights.Queen

    Devuelve
    --------
    DataFrame con columnas 'barrio' y 'bloque_cv'.
    """
    barrios_en_metros = barrios_gdf.to_crs(CRS_METRICO)
    centroides = barrios_en_metros.geometry.centroid
    coordenadas_de_centroides = pd.DataFrame(
        {"x": centroides.x, "y": centroides.y}
    ).to_numpy()

    matriz_de_contiguidad = pesos_queen.sparse

    # El protocolo (§ 6, paso 4) fija que ningún bloque puede tener menos de 6
    # barrios: un fold demasiado chico no permite estimar el error con
    # estabilidad. Si con 5 bloques alguno queda corto, se baja a 4. La regla
    # estaba escrita de antemano, así que la decisión no depende del resultado.
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
    print(
        f"  tamaños: {bloques['bloque_cv'].value_counts().sort_index().to_dict()}"
    )

    return bloques


def dibujar_mapa_de_control(eventos_con_barrio, barrios_gdf, bloques, ruta_de_salida):
    """
    Dibuja el mapa de control y lo guarda como PNG.

    Objetivo
    --------
    Es la herramienta de QA más eficiente que existe para datos espaciales. Una
    tabla dice "98,5 % con coordenadas" y suena perfecto; un mapa muestra en dos
    segundos si 200 puntos cayeron en el Río de la Plata, o si hay un cluster en
    latitud 0 / longitud 0 (el Golfo de Guinea), que es lo que pasa cuando una
    geocodificación fallida devuelve ceros en vez de nulos.

    Se dibujan tres paneles:
      1. los puntos sobre los polígonos, para detectar puntos fuera de lugar
      2. la cantidad de eventos por barrio, para ver la concentración
      3. los bloques de CV, para verificar que cada uno sea contiguo

    Inputs
    ------
    eventos_con_barrio : GeoDataFrame
    barrios_gdf : GeoDataFrame
    bloques : DataFrame con 'barrio' y 'bloque_cv'
    ruta_de_salida : Path
    """
    figura, paneles = plt.subplots(1, 3, figsize=(21, 7))

    # Panel 1 — puntos crudos sobre los polígonos.
    barrios_gdf.boundary.plot(ax=paneles[0], color="0.6", linewidth=0.5)
    eventos_con_barrio.plot(
        ax=paneles[0], markersize=2, alpha=0.25, color="crimson"
    )
    paneles[0].set_title(
        f"Eventos geolocalizados (n={len(eventos_con_barrio)})\n"
        "buscar puntos fuera de los polígonos"
    )

    # Panel 2 — concentración por barrio.
    conteo_por_barrio = (
        eventos_con_barrio.groupby("barrio_normalizado").size().rename("n_eventos")
    )
    barrios_con_conteo = barrios_gdf.merge(
        conteo_por_barrio, left_on="barrio_normalizado", right_index=True, how="left"
    )
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

    # Panel 3 — bloques de CV espacial.
    barrios_con_bloque = barrios_gdf.merge(
        bloques, left_on="barrio_normalizado", right_on="barrio", how="left"
    )
    barrios_con_bloque.plot(
        ax=paneles[2],
        column="bloque_cv",
        cmap="tab10",
        edgecolor="white",
        linewidth=0.8,
        categorical=True,
        legend=True,
    )
    paneles[2].set_title(
        "Bloques de CV espacial\ncada color debe ser una mancha contigua"
    )

    for panel in paneles:
        panel.set_axis_off()

    figura.tight_layout()
    figura.savefig(ruta_de_salida, dpi=130, bbox_inches="tight")
    plt.close(figura)
    print(f"  mapa de control guardado en {ruta_de_salida.name}")


def main():
    """Orquesta la etapa completa. Todo el efecto secundario vive acá."""
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
    eventos_con_barrio = asignar_barrio_por_point_in_polygon(
        eventos_gdf, barrios, columna_de_barrio
    )

    cantidad_sin_barrio = eventos_con_barrio["barrio"].isna().sum()
    cantidad_con_barrio = len(eventos_con_barrio) - cantidad_sin_barrio
    print(
        f"  dentro de CABA: {cantidad_con_barrio} "
        f"({cantidad_con_barrio / len(eventos_con_barrio):.1%})"
    )
    print(f"  fuera de CABA:  {cantidad_sin_barrio} (esperable: GBA)")

    print("\n[4/6] Control cruzado contra el barrio declarado por la fuente")
    comparar_contra_barrio_declarado(eventos_con_barrio)

    print("\n[5/6] Matriz de contigüidad queen y bloques de CV espacial")
    pesos_queen = construir_matriz_de_contiguidad_queen(barrios, columna_de_barrio)
    bloques = definir_bloques_de_cv_espacial(barrios, columna_de_barrio, pesos_queen)

    # Se persiste la partición y no se recalcula en cada corrida: si cambia,
    # cambian los folds, y los resultados dejan de ser comparables entre sí.
    DIRECTORIO_PROCESADO.mkdir(parents=True, exist_ok=True)
    ruta_bloques = DIRECTORIO_PROCESADO / "bloques_cv.csv"
    bloques_para_guardar = bloques.copy()
    bloques_para_guardar["barrio"] = bloques_para_guardar["barrio"].map(
        normalizar_texto_para_comparar
    )
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

    eventos_dentro_de_caba = eventos_con_barrio.dropna(subset=["barrio"]).drop(
        columns=["geometry"]
    )
    ruta_salida = DIRECTORIO_INTERMEDIO / "eventos_geolocalizados.parquet"
    eventos_dentro_de_caba.to_parquet(ruta_salida, index=False)

    eventos_del_panel = eventos_dentro_de_caba[
        ~eventos_dentro_de_caba["fecha"].dt.year.isin([2020, 2021])
    ]

    print(f"\n{'=' * 66}")
    print("GATE DE LA ETAPA 2")
    print(f"  geocodificados:     {cantidad_con_barrio / len(eventos):.1%}  (>= 85 %)")
    print(f"  barrios con evento: {eventos_del_panel['barrio'].nunique()}  (>= 40)")
    print(f"  eventos del panel:  {len(eventos_del_panel)}  (>= 3000)")
    print(f"\nEscrito: {ruta_salida.name}")
    print(f"{'=' * 66}")


if __name__ == "__main__":
    main()
