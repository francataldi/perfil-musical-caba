"""
Verificación externa de src/composicional.py contra composition-stats.

Por qué existe este archivo aparte
----------------------------------
Los tests de propiedad de test_composicional.py verifican que la implementación
sea INTERNAMENTE CONSISTENTE: que ilr_inv deshaga a ilr, que la base sea
ortonormal, que la distancia sea invariante. Todo eso puede cumplirse
perfectamente y estar mal, si el error está en cómo entendí la fórmula y lo
apliqué de forma coherente en todos lados.

El control externo es lo único que descarta esa clase de error. Es el último
ítem del gate de la Etapa 5.

Nota sobre la base de ILR
-------------------------
composition-stats usa la base de Helmert (particiones secuenciales por defecto),
no la SBP del proyecto. Dos bases ortonormales distintas del mismo hiperplano
dan coordenadas distintas, así que NO se comparan coordenada a coordenada: se
comparan las cantidades que son invariantes al cambio de base, que son las que
realmente importan (la norma, la distancia, y el resultado de CLR).
"""

import numpy as np
import pytest

from src.composicional import (
    GENRES,
    aitchison_distance,
    clr,
    closure,
    ilr,
    project_ilr_basis,
)

composition_stats = pytest.importorskip(
    "composition_stats",
    reason="composition-stats no está instalado; se instala con environment.yml",
)

RANDOM_SEED = 20260805
N_GENRES = len(GENRES)
NUMERIC_TOLERANCE = 1e-10


@pytest.fixture
def composition_sample():
    random_generator = np.random.default_rng(RANDOM_SEED)
    return closure(random_generator.dirichlet(np.ones(N_GENRES), size=100))


def test_closure_coincide_con_la_libreria(composition_sample):
    assert np.allclose(
        closure(composition_sample),
        composition_stats.closure(composition_sample),
        atol=NUMERIC_TOLERANCE,
    )


def test_clr_coincide_con_la_libreria(composition_sample):
    # CLR no depende de ninguna elección de base, así que acá sí se comparan
    # las coordenadas una por una.
    assert np.allclose(
        clr(composition_sample),
        composition_stats.clr(composition_sample),
        atol=NUMERIC_TOLERANCE,
    )


def test_norma_ilr_coincide_pese_a_usar_bases_distintas(composition_sample):
    # La norma del vector de coordenadas es invariante al cambio de base
    # ortonormal. Si mi base no fuera ortonormal, esto fallaría.
    project_basis = project_ilr_basis()

    norm_with_project_basis = np.linalg.norm(
        ilr(composition_sample, project_basis), axis=1
    )
    norm_with_library_basis = np.linalg.norm(
        composition_stats.ilr(composition_sample), axis=1
    )

    assert np.allclose(
        norm_with_project_basis, norm_with_library_basis, atol=NUMERIC_TOLERANCE
    )


def test_distancia_aitchison_coincide_con_la_calculada_en_la_base_de_la_libreria(
    composition_sample,
):
    first_half = composition_sample[:50]
    second_half = composition_sample[50:]

    distance_from_library_ilr = np.linalg.norm(
        composition_stats.ilr(first_half) - composition_stats.ilr(second_half),
        axis=1,
    )

    assert np.allclose(
        aitchison_distance(first_half, second_half),
        distance_from_library_ilr,
        atol=NUMERIC_TOLERANCE,
    )


def test_ilr_inversa_de_la_libreria_reconstruye_mis_composiciones(composition_sample):
    # Cruce completo: transformo con la librería, reconstruyo con la librería, y
    # verifico contra el input que mi closure() produjo.
    library_coordinates = composition_stats.ilr(composition_sample)
    reconstructed = composition_stats.ilr_inv(library_coordinates)

    assert np.allclose(reconstructed, composition_sample, atol=NUMERIC_TOLERANCE)
