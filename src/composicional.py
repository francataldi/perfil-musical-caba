"""
Operaciones sobre el símplex S^D y transformaciones log-razón.

El símplex (D componentes positivas que suman 1) NO es un espacio vectorial
euclídeo: sumar dos composiciones o multiplicarlas por un escalar saca del
conjunto. Este módulo implementa las operaciones que sí respetan su geometría.

Convención de shapes: toda función acepta un vector (D,) o una matriz (n, D)
donde cada FILA es una composición, y devuelve el mismo formato.

Precondición global: todas las partes estrictamente positivas.
Los ceros se tratan en el módulo de la Etapa 4, NO acá.

Respaldo teórico: docs/fundamentos.pdf y docs/aprendizaje/.

Referencias:
    Aitchison, J. (1986). The Statistical Analysis of Compositional Data.
    Egozcue et al. (2003). Isometric logratio transformations. Math. Geology 35(3).
"""

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# Operaciones básicas del símplex
# ─────────────────────────────────────────────────────────────────────────────


def closure(raw_parts):
    """
    Lleva partes positivas al símplex, dividiendo cada fila por su suma.

    Objetivo
    --------
    Normalizar conteos o proporciones para que vivan en el símplex, que es la
    precondición de toda transformación log-razón. El cierre preserva las
    razones entre partes: x_i/x_j no cambia. Esa es exactamente la información
    que la geometría de Aitchison considera relevante.

    Inputs
    ------
    raw_parts : array (D,) o (n, D)
        Partes estrictamente positivas, sin normalizar.

    Devuelve
    --------
    array del mismo shape, con cada fila sumando 1.

    Raises
    ------
    ValueError si alguna parte es <= 0.
    """
    raw_parts = np.asarray(raw_parts, dtype=float)

    # Se falla ruidosamente en vez de devolver NaN: un cero acá significa que el
    # tratamiento de ceros de la Etapa 4 no se ejecutó. Es un error de pipeline
    # que tiene que detenerse en el punto de origen y no propagarse en silencio
    # hasta un gráfico raro tres etapas después.
    if np.any(raw_parts <= 0):
        raise ValueError(
            "closure() requiere partes estrictamente positivas. "
            "Los ceros se tratan antes con reemplazo multiplicativo bayesiano."
        )

    total_per_composition = raw_parts.sum(axis=-1, keepdims=True)
    return raw_parts / total_per_composition


def geometric_mean(compositions):
    """
    Media geométrica de las partes, por fila (dentro de cada composición).

    Objetivo
    --------
    Es el denominador de la transformación CLR. Se usa la media geométrica y no
    la aritmética porque es el único centro que respeta las razones: escalar
    todas las partes por una constante escala la media geométrica por esa misma
    constante.

    Inputs
    ------
    compositions : array (D,) o (n, D)
        Partes estrictamente positivas.

    Devuelve
    --------
    float si la entrada es 1D, o array (n, 1) si es 2D (shape apto para
    broadcasting contra la matriz original).
    """
    compositions = np.asarray(compositions, dtype=float)

    # Se calcula como exp(mean(log(x))) y no como prod(x)**(1/D) porque el
    # producto de 8 partes del orden de 1e-3 da 1e-24, que pierde precisión, y
    # con más partes directamente hace underflow a cero. En espacio logarítmico
    # se suman magnitudes chicas en vez de multiplicarlas.
    log_parts = np.log(compositions)

    if compositions.ndim == 1:
        return float(np.exp(np.mean(log_parts)))
    return np.exp(np.mean(log_parts, axis=-1, keepdims=True))


def center(compositions_sample):
    """
    Centro de un conjunto de composiciones: media geométrica cerrada.

    Objetivo
    --------
    Es el análogo composicional de la media aritmética y el sustituto correcto
    de np.mean() sobre proporciones. Promediar composiciones aritméticamente da
    un vector que no representa al conjunto: sobrepondera las partes grandes y
    no respeta las razones.

    Implementa el baseline B0 del protocolo.

    OJO, distinción que se olvida rápido
    ------------------------------------
    geometric_mean() opera POR FILA (dentro de una composición) y devuelve un
    escalar por observación. center() opera A LO LARGO DE LA MUESTRA (por
    columna) y devuelve una sola composición que resume a todas.

    Inputs
    ------
    compositions_sample : array (n, D)
        Las n composiciones a resumir.

    Devuelve
    --------
    array (D,) cerrado: una única composición.
    """
    # Promediar en el espacio CLR y volver equivale a la media geométrica por
    # columna seguida de cierre, pero se apoya en código ya testeado.
    mean_clr_coordinates = np.mean(clr(compositions_sample), axis=0)
    return clr_inv(mean_clr_coordinates)


def perturbation(composition, perturbing_composition):
    """
    x ⊕ y: la operación "suma" del símplex.

    Objetivo
    --------
    En el símplex la suma vectorial no es válida (saca del conjunto). Su
    análogo correcto es el producto componente a componente seguido de cierre.
    Cumple el rol de la traslación en R^D: la distancia de Aitchison es
    invariante ante ella, propiedad que se testea para verificar que toda la
    implementación es correcta.

    Inputs
    ------
    composition : array (D,) o (n, D)
        Composición o conjunto de composiciones a perturbar.
    perturbing_composition : array (D,)
        El vector de perturbación.

    Devuelve
    --------
    array cerrado, mismo shape que composition.
    """
    return closure(
        np.asarray(composition, dtype=float)
        * np.asarray(perturbing_composition, dtype=float)
    )


def powering(exponent, composition):
    """
    alpha ⊙ x: la operación "producto por escalar" del símplex.

    Objetivo
    --------
    Eleva cada parte a la potencia dada y cierra. Junto con perturbation(), le
    da al símplex estructura de espacio vectorial (de Hilbert, con el producto
    interno de Aitchison), que es lo que legitima hacer estadística lineal
    sobre él una vez transformado.

    Inputs
    ------
    exponent : float
        El escalar alpha.
    composition : array (D,) o (n, D)

    Devuelve
    --------
    array cerrado, mismo shape que composition.
    """
    return closure(np.asarray(composition, dtype=float) ** float(exponent))


# ─────────────────────────────────────────────────────────────────────────────
# Transformación CLR (centered log-ratio)
# ─────────────────────────────────────────────────────────────────────────────


def clr(compositions):
    """
    Centered log-ratio: log de cada parte sobre la media geométrica de su fila.

    Objetivo
    --------
    Llevar del símplex a un hiperplano de R^D donde las coordenadas son
    simétricas respecto de las partes: hay una coordenada por género, con el
    mismo nombre. Se usa para VISUALIZAR — biplot, PCA, matriz de variación.

    No se modela directamente en CLR: las filas suman cero por construcción,
    así que la matriz de covarianza es singular y cualquier regresión
    multivariada sobre estas coordenadas es degenerada. Para modelar, ILR.

    Inputs
    ------
    compositions : array (D,) o (n, D)
        Se cierra internamente; no hace falta que ya sume 1.

    Devuelve
    --------
    array del mismo shape, con cada fila sumando 0.
    """
    closed_parts = closure(compositions)

    # Restar la media de los logs equivale a dividir por la media geométrica:
    # log(x_i / g(x)) = log(x_i) - log(g(x)) = log(x_i) - mean(log(x)).
    return np.log(closed_parts) - np.log(geometric_mean(closed_parts))


def clr_inv(clr_coordinates):
    """
    Inversa de clr(): exponenciar y cerrar.

    Objetivo
    --------
    Volver del hiperplano CLR al símplex. Se usa para llevar predicciones o
    componentes principales de vuelta al espacio de proporciones interpretables.

    Inputs
    ------
    clr_coordinates : array (D,) o (n, D)
        Coordenadas CLR, típicamente sumando cero por fila.

    Devuelve
    --------
    array cerrado, mismo shape.
    """
    return closure(np.exp(np.asarray(clr_coordinates, dtype=float)))


# ─────────────────────────────────────────────────────────────────────────────
# Transformación ILR (isometric log-ratio)
# ─────────────────────────────────────────────────────────────────────────────


def ilr_basis_from_sbp(sbp_matrix):
    """
    Construye la base ortonormal de ILR a partir de una secuencia de
    particiones binarias (SBP).

    Objetivo
    --------
    ILR necesita una base ortonormal del hiperplano CLR. Esta función la deriva
    de una SBP, que codifica D-1 particiones sucesivas del conjunto de partes.
    Elegir la SBP con criterio sustantivo hace que cada coordenada ILR sea un
    balance interpretable, y eso se traduce después en coeficientes de regresión
    legibles ("una comuna más envejecida se asocia a un balance tango/folklore
    más alto") en lugar de combinaciones lineales opacas.

    Cada columna de la SBP define un balance entre el grupo marcado +1
    (r partes) y el grupo marcado -1 (s partes). El vector correspondiente de
    la base, en coordenadas CLR, es:

        psi_i = +sqrt(s / (r*(r+s)))   si la parte i está en el grupo +1
        psi_i = -sqrt(r / (s*(r+s)))   si la parte i está en el grupo -1
        psi_i =  0                     si la parte i no participa

    Inputs
    ------
    sbp_matrix : array (D, D-1) con valores en {-1, 0, +1}
        Una fila por parte, una columna por balance.

    Devuelve
    --------
    array (D, D-1): la base ortonormal V, que cumple V.T @ V = I.

    Raises
    ------
    ValueError si el shape no es (D, D-1), si hay valores fuera de {-1,0,1},
    o si algún balance no tiene partes en ambos lados.
    """
    sbp_matrix = np.asarray(sbp_matrix, dtype=float)
    n_parts, n_balances = sbp_matrix.shape

    # Una SBP sobre D partes tiene que producir exactamente D-1 balances: es la
    # dimensión del hiperplano CLR. Con menos, la base no lo genera; con más,
    # las columnas no pueden ser todas ortogonales entre sí.
    if n_balances != n_parts - 1:
        raise ValueError(
            f"Una SBP sobre {n_parts} partes necesita exactamente {n_parts - 1} "
            f"balances; se recibieron {n_balances}."
        )
    if not np.all(np.isin(sbp_matrix, (-1.0, 0.0, 1.0))):
        raise ValueError("La matriz SBP solo admite valores -1, 0 y +1.")

    orthonormal_basis = np.zeros_like(sbp_matrix)

    for balance_index in range(n_balances):
        balance_column = sbp_matrix[:, balance_index]
        is_numerator_part = balance_column == 1
        is_denominator_part = balance_column == -1
        n_numerator_parts = is_numerator_part.sum()
        n_denominator_parts = is_denominator_part.sum()

        if n_numerator_parts == 0 or n_denominator_parts == 0:
            raise ValueError(
                f"El balance {balance_index} no parte el conjunto en dos grupos "
                "no vacíos: falta al menos un +1 o un -1."
            )

        n_parts_in_balance = n_numerator_parts + n_denominator_parts

        # Esta normalización es la que garantiza norma 1. La ortogonalidad entre
        # columnas la garantiza la estructura anidada de la SBP: dos balances o
        # bien actúan sobre grupos disjuntos, o uno actúa dentro de un grupo que
        # el otro trata como un bloque homogéneo.
        orthonormal_basis[is_numerator_part, balance_index] = np.sqrt(
            n_denominator_parts / (n_numerator_parts * n_parts_in_balance)
        )
        orthonormal_basis[is_denominator_part, balance_index] = -np.sqrt(
            n_numerator_parts / (n_denominator_parts * n_parts_in_balance)
        )

    return orthonormal_basis


def ilr(compositions, orthonormal_basis):
    """
    Isometric log-ratio: proyecta las coordenadas CLR sobre la base ortonormal.

    Objetivo
    --------
    ILR es una ISOMETRÍA del símplex a R^(D-1): preserva distancias y ángulos.
    Eso es lo que habilita usar estadística multivariada estándar (regresión
    lineal, efectos aleatorios, PCA) sobre las coordenadas y volver al símplex
    con la inversa sin haber distorsionado nada por el camino.

    A diferencia de CLR, la covarianza en ILR es de rango completo, así que la
    regresión no es degenerada. De ahí la regla del proyecto: se modela en ILR,
    se visualiza en CLR.

    Inputs
    ------
    compositions : array (D,) o (n, D)
    orthonormal_basis : array (D, D-1)
        Salida de ilr_basis_from_sbp().

    Devuelve
    --------
    array (D-1,) o (n, D-1): las coordenadas de balance.
    """
    return clr(compositions) @ np.asarray(orthonormal_basis, dtype=float)


def ilr_inv(ilr_coordinates, orthonormal_basis):
    """
    Inversa de ilr(): vuelve de las coordenadas de balance al símplex.

    Objetivo
    --------
    Convierte una predicción del modelo (que vive en R^(D-1)) en una composición
    de proporciones interpretable. Como la reconstrucción pasa por exponenciar y
    cerrar, el resultado siempre cae dentro del símplex: el modelo no puede
    predecir proporciones negativas ni que no sumen 1. Esa garantía sale gratis
    de la geometría, sin restricciones explícitas en el optimizador.

    Inputs
    ------
    ilr_coordinates : array (D-1,) o (n, D-1)
    orthonormal_basis : array (D, D-1)
        La MISMA base que se usó en ilr(); con otra, el resultado no tiene sentido.

    Devuelve
    --------
    array (D,) o (n, D), cerrado.
    """
    orthonormal_basis = np.asarray(orthonormal_basis, dtype=float)
    reconstructed_clr = np.asarray(ilr_coordinates, dtype=float) @ orthonormal_basis.T
    return clr_inv(reconstructed_clr)


# ─────────────────────────────────────────────────────────────────────────────
# Métricas y estadísticos descriptivos
# ─────────────────────────────────────────────────────────────────────────────


def aitchison_distance(first_composition, second_composition):
    """
    Distancia de Aitchison entre composiciones.

    Objetivo
    --------
    Es la métrica correcta en el símplex: la distancia euclídea entre las
    coordenadas CLR. Sus dos propiedades clave son la invarianza ante
    perturbación (el análogo de la invarianza ante traslación en R^D) y la
    invarianza ante subcomposiciones (mirar solo un subconjunto de géneros no
    altera la distancia relativa entre los que quedan).

    Es la métrica interpretable del protocolo: cuán lejos está la composición
    predicha de la observada.

    Inputs
    ------
    first_composition : array (D,) o (n, D)
    second_composition : array (D,) o (n, D)

    Devuelve
    --------
    float si ambas son 1D, o array (n,) si son 2D.
    """
    clr_difference = clr(first_composition) - clr(second_composition)
    return np.sqrt(np.sum(clr_difference**2, axis=-1))


def variation_matrix(compositions_sample, ddof=1):
    """
    Matriz de variación: tau_ij = Var[log(x_i / x_j)].

    Objetivo
    --------
    Es el sustituto correcto de la matriz de correlación de Pearson, que en
    datos composicionales es espuria por construcción (Pearson, 1897): si las
    partes suman 1, cuando una sube las otras bajan por fuerza algebraica, así
    que una correlación negativa entre dos géneros no informa nada sobre el
    mundo.

    Interpretación: tau_ij cercano a 0 significa que las dos partes se mueven
    proporcionalmente entre observaciones (su razón es casi constante). Valores
    altos indican que varían de forma independiente. La matriz no tiene escala
    acotada como una correlación: se lee comparando entradas entre sí, no
    contra un umbral fijo.

    Inputs
    ------
    compositions_sample : array (n, D)
        Las n composiciones de la muestra.
    ddof : int, default 1
        Varianza muestral (ddof=1), no poblacional. La decisión es explícita y
        no heredada del default de numpy (ddof=0): las n celdas barrio-trimestre
        son una muestra de la oferta posible, no la población entera de eventos
        que podrían haber ocurrido.

    Devuelve
    --------
    array (D, D) simétrico con diagonal nula.
    """
    log_transformed_parts = np.log(closure(compositions_sample))

    # Vectorizado por broadcasting: log(x_i/x_j) = log(x_i) - log(x_j), así que
    # todas las diferencias de a pares salen de restar la matriz de logs consigo
    # misma sobre ejes distintos, sin doble loop en Python.
    # Shape resultante: (n, D, D), con [k, i, j] = log(x_ki) - log(x_kj).
    pairwise_log_ratios = (
        log_transformed_parts[:, :, None] - log_transformed_parts[:, None, :]
    )

    return np.var(pairwise_log_ratios, axis=0, ddof=ddof)


# ─────────────────────────────────────────────────────────────────────────────
# SBP del proyecto — orden y balances fijados de una vez para todo el análisis
# ─────────────────────────────────────────────────────────────────────────────

GENRES = ("ROCK", "TROP", "FOLK", "TANG", "JAZZ", "ELEC", "CLAS", "OTRO")

# Cada columna es un balance: +1 numerador, -1 denominador, 0 no participa.
# La SBP es válida porque cada balance parte un grupo ya formado por los
# balances anteriores; nunca cruza la jerarquía.
#
#   b1  raíz argentina/rioplatense   {TANG,FOLK}  vs  el resto
#   b2  dentro de raíz               TANG         vs  FOLK
#   b3  baile vs escucha             {TROP,ELEC}  vs  {ROCK,JAZZ,CLAS,OTRO}
#   b4  dentro de baile              TROP         vs  ELEC
#   b5  culta vs popular             {JAZZ,CLAS}  vs  {ROCK,OTRO}
#   b6  dentro de culta              JAZZ         vs  CLAS
#   b7  resto popular                ROCK         vs  OTRO
SBP_GENRES = np.array(
    [
        # b1  b2  b3  b4  b5  b6  b7
        [-1,  0, -1,  0, -1,  0,  1],  # ROCK
        [-1,  0,  1,  1,  0,  0,  0],  # TROP
        [ 1, -1,  0,  0,  0,  0,  0],  # FOLK
        [ 1,  1,  0,  0,  0,  0,  0],  # TANG
        [-1,  0, -1,  0,  1,  1,  0],  # JAZZ
        [-1,  0,  1, -1,  0,  0,  0],  # ELEC
        [-1,  0, -1,  0,  1, -1,  0],  # CLAS
        [-1,  0, -1,  0, -1,  0, -1],  # OTRO
    ],
    dtype=float,
)

BALANCE_NAMES = (
    "raiz_vs_resto",
    "tango_vs_folklore",
    "baile_vs_escucha",
    "tropical_vs_electronica",
    "culta_vs_popular",
    "jazz_vs_clasica",
    "rock_vs_otro",
)


def project_ilr_basis():
    """
    Devuelve la base ortonormal ILR derivada de la SBP del proyecto.

    Objetivo
    --------
    Punto de entrada único para que todos los notebooks, scripts y modelos usen
    exactamente la misma base. Si cada módulo construyera la suya, los
    coeficientes dejarían de ser comparables entre análisis — la misma lección
    que motivó centralizar la taxonomía en config/taxonomia_generos.yaml.

    Devuelve
    --------
    array (8, 7) ortonormal, con las columnas en el orden de BALANCE_NAMES.
    """
    return ilr_basis_from_sbp(SBP_GENRES)
