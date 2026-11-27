import numpy as np
import pytest

from src.composicional import (
    BALANCE_NAMES,
    GENRES,
    SBP_GENRES,
    aitchison_distance,
    center,
    closure,
    clr,
    clr_inv,
    geometric_mean,
    ilr,
    ilr_basis_from_sbp,
    ilr_inv,
    perturbation,
    powering,
    project_ilr_basis,
    variation_matrix,
)

RANDOM_SEED = 20260801
N_GENRES = len(GENRES)
NUMERIC_TOLERANCE = 1e-10
UNIFORM_COMPOSITION = np.full(N_GENRES, 1.0 / N_GENRES)


@pytest.fixture
def random_generator():
    return np.random.default_rng(RANDOM_SEED)


@pytest.fixture
def single_composition(random_generator):
    return closure(random_generator.dirichlet(np.ones(N_GENRES)))


@pytest.fixture
def composition_sample(random_generator):
    return closure(random_generator.dirichlet(np.ones(N_GENRES), size=50))


@pytest.fixture
def project_basis():
    return project_ilr_basis()


def test_closure_suma_uno(composition_sample):
    assert np.allclose(composition_sample.sum(axis=1), 1.0, atol=NUMERIC_TOLERANCE)


def test_closure_preserva_razones(random_generator):
    raw_counts = random_generator.integers(1, 500, size=N_GENRES).astype(float)
    closed_counts = closure(raw_counts)

    ratios_before_closure = raw_counts[:, None] / raw_counts[None, :]
    ratios_after_closure = closed_counts[:, None] / closed_counts[None, :]

    assert np.allclose(ratios_before_closure, ratios_after_closure, atol=NUMERIC_TOLERANCE)


def test_closure_es_idempotente(composition_sample):
    assert np.allclose(closure(composition_sample), composition_sample, atol=NUMERIC_TOLERANCE)


def test_closure_rechaza_ceros():
    with pytest.raises(ValueError):
        closure(np.array([0.5, 0.0, 0.5]))


def test_closure_rechaza_negativos():
    with pytest.raises(ValueError):
        closure(np.array([0.5, -0.2, 0.7]))


def test_geometric_mean_de_composicion_constante_es_la_constante():
    assert np.isclose(geometric_mean(UNIFORM_COMPOSITION), 1.0 / N_GENRES, atol=NUMERIC_TOLERANCE)


def test_geometric_mean_escala_con_las_partes(single_composition):
    scaling_factor = 7.3

    assert np.isclose(
        geometric_mean(single_composition * scaling_factor),
        scaling_factor * geometric_mean(single_composition),
        atol=NUMERIC_TOLERANCE,
    )


def test_geometric_mean_no_hace_underflow():
    very_small_parts = np.full(300, 1e-8)

    assert geometric_mean(very_small_parts) > 0
    assert np.isclose(geometric_mean(very_small_parts), 1e-8, rtol=1e-9)


def test_center_devuelve_una_composicion(composition_sample):
    sample_center = center(composition_sample)

    assert sample_center.shape == (N_GENRES,)
    assert np.isclose(sample_center.sum(), 1.0, atol=NUMERIC_TOLERANCE)


def test_center_de_replicas_es_la_composicion_original(single_composition):
    repeated_compositions = np.tile(single_composition, (25, 1))

    assert np.allclose(center(repeated_compositions), single_composition, atol=NUMERIC_TOLERANCE)


def test_center_es_equivariante_ante_perturbacion(composition_sample, random_generator):
    perturbing_composition = closure(random_generator.dirichlet(np.ones(N_GENRES)))

    assert np.allclose(
        center(perturbation(composition_sample, perturbing_composition)),
        perturbation(center(composition_sample), perturbing_composition),
        atol=NUMERIC_TOLERANCE,
    )


def test_perturbation_tiene_elemento_neutro(single_composition):
    assert np.allclose(
        perturbation(single_composition, UNIFORM_COMPOSITION),
        single_composition,
        atol=NUMERIC_TOLERANCE,
    )


def test_perturbation_tiene_elemento_inverso(single_composition):
    inverse_composition = closure(1.0 / single_composition)

    assert np.allclose(
        perturbation(single_composition, inverse_composition),
        UNIFORM_COMPOSITION,
        atol=NUMERIC_TOLERANCE,
    )


def test_perturbation_es_conmutativa(random_generator):
    first_composition = closure(random_generator.dirichlet(np.ones(N_GENRES)))
    second_composition = closure(random_generator.dirichlet(np.ones(N_GENRES)))

    assert np.allclose(
        perturbation(first_composition, second_composition),
        perturbation(second_composition, first_composition),
        atol=NUMERIC_TOLERANCE,
    )


def test_powering_por_uno_es_la_identidad(single_composition):
    assert np.allclose(powering(1.0, single_composition), single_composition, atol=NUMERIC_TOLERANCE)


def test_powering_por_cero_da_el_elemento_neutro(single_composition):
    assert np.allclose(
        powering(0.0, single_composition),
        UNIFORM_COMPOSITION,
        atol=NUMERIC_TOLERANCE,
    )


def test_clr_suma_cero_por_fila(composition_sample):
    assert np.allclose(clr(composition_sample).sum(axis=1), 0.0, atol=NUMERIC_TOLERANCE)


def test_clr_ida_y_vuelta(composition_sample):
    assert np.allclose(clr_inv(clr(composition_sample)), composition_sample, atol=NUMERIC_TOLERANCE)


def test_clr_es_invariante_al_cierre(random_generator):
    raw_counts = random_generator.integers(1, 500, size=N_GENRES).astype(float)

    assert np.allclose(clr(raw_counts), clr(raw_counts * 137.0), atol=NUMERIC_TOLERANCE)


def test_clr_convierte_perturbacion_en_suma(single_composition, random_generator):
    perturbing_composition = closure(random_generator.dirichlet(np.ones(N_GENRES)))

    assert np.allclose(
        clr(perturbation(single_composition, perturbing_composition)),
        clr(single_composition) + clr(perturbing_composition),
        atol=NUMERIC_TOLERANCE,
    )


def test_clr_produce_covarianza_singular(composition_sample):
    clr_covariance = np.cov(clr(composition_sample), rowvar=False)

    assert np.linalg.matrix_rank(clr_covariance, tol=1e-8) == N_GENRES - 1


def test_base_ilr_es_ortonormal(project_basis):
    assert np.allclose(
        project_basis.T @ project_basis,
        np.eye(N_GENRES - 1),
        atol=NUMERIC_TOLERANCE,
    )


def test_base_ilr_vive_en_el_hiperplano_clr(project_basis):
    assert np.allclose(project_basis.sum(axis=0), 0.0, atol=NUMERIC_TOLERANCE)


def test_base_ilr_reconstruye_el_proyector_del_hiperplano(project_basis):
    hyperplane_projector = np.eye(N_GENRES) - np.ones((N_GENRES, N_GENRES)) / N_GENRES

    assert np.allclose(
        project_basis @ project_basis.T,
        hyperplane_projector,
        atol=NUMERIC_TOLERANCE,
    )


def test_sbp_del_proyecto_tiene_forma_correcta():
    assert SBP_GENRES.shape == (len(GENRES), len(GENRES) - 1)
    assert len(BALANCE_NAMES) == len(GENRES) - 1


def test_sbp_rechaza_cantidad_incorrecta_de_balances():
    incomplete_sbp = np.array([[1, 0], [-1, 1], [0, -1], [0, 0]], dtype=float)

    with pytest.raises(ValueError):
        ilr_basis_from_sbp(incomplete_sbp)


def test_sbp_rechaza_balance_con_un_solo_lado():
    sbp_with_empty_denominator = np.array([[1, 1], [1, -1], [1, 0]], dtype=float)

    with pytest.raises(ValueError):
        ilr_basis_from_sbp(sbp_with_empty_denominator)


def test_sbp_rechaza_valores_fuera_del_dominio():
    sbp_with_invalid_value = np.array([[2, -1], [-1, 1], [-1, 0]], dtype=float)

    with pytest.raises(ValueError):
        ilr_basis_from_sbp(sbp_with_invalid_value)


def test_ilr_ida_y_vuelta_sobre_una_muestra(composition_sample, project_basis):
    assert np.allclose(
        ilr_inv(ilr(composition_sample, project_basis), project_basis),
        composition_sample,
        atol=NUMERIC_TOLERANCE,
    )


def test_ilr_ida_y_vuelta_sobre_un_vector_suelto(single_composition, project_basis):
    assert np.allclose(
        ilr_inv(ilr(single_composition, project_basis), project_basis),
        single_composition,
        atol=NUMERIC_TOLERANCE,
    )


def test_ilr_reduce_una_dimension(composition_sample, project_basis):
    assert ilr(composition_sample, project_basis).shape == (
        len(composition_sample),
        N_GENRES - 1,
    )


def test_ilr_es_una_isometria(random_generator, project_basis):
    first_sample = closure(random_generator.dirichlet(np.ones(N_GENRES), size=30))
    second_sample = closure(random_generator.dirichlet(np.ones(N_GENRES), size=30))

    euclidean_distance_in_ilr = np.linalg.norm(ilr(first_sample, project_basis) - ilr(second_sample, project_basis), axis=1)

    assert np.allclose(
        euclidean_distance_in_ilr,
        aitchison_distance(first_sample, second_sample),
        atol=NUMERIC_TOLERANCE,
    )


def test_ilr_convierte_perturbacion_en_suma(single_composition, project_basis, random_generator):
    perturbing_composition = closure(random_generator.dirichlet(np.ones(N_GENRES)))

    assert np.allclose(
        ilr(perturbation(single_composition, perturbing_composition), project_basis),
        ilr(single_composition, project_basis) + ilr(perturbing_composition, project_basis),
        atol=NUMERIC_TOLERANCE,
    )


def test_ilr_del_elemento_neutro_es_el_origen(project_basis):
    assert np.allclose(ilr(UNIFORM_COMPOSITION, project_basis), 0.0, atol=NUMERIC_TOLERANCE)


def test_primer_balance_separa_raiz_del_resto(project_basis):
    balance_index = BALANCE_NAMES.index("raiz_vs_resto")

    composition_with_more_roots = UNIFORM_COMPOSITION.copy()
    composition_with_more_roots[GENRES.index("TANG")] *= 4.0
    composition_with_more_roots[GENRES.index("FOLK")] *= 4.0
    composition_with_more_roots = closure(composition_with_more_roots)

    assert ilr(composition_with_more_roots, project_basis)[balance_index] > ilr(UNIFORM_COMPOSITION, project_basis)[balance_index]


def test_distancia_de_una_composicion_a_si_misma_es_cero(single_composition):
    assert np.isclose(
        aitchison_distance(single_composition, single_composition),
        0.0,
        atol=NUMERIC_TOLERANCE,
    )


def test_distancia_es_simetrica(random_generator):
    first_composition = closure(random_generator.dirichlet(np.ones(N_GENRES)))
    second_composition = closure(random_generator.dirichlet(np.ones(N_GENRES)))

    assert np.isclose(
        aitchison_distance(first_composition, second_composition),
        aitchison_distance(second_composition, first_composition),
        atol=NUMERIC_TOLERANCE,
    )


def test_distancia_es_invariante_ante_perturbacion(random_generator):
    first_sample = closure(random_generator.dirichlet(np.ones(N_GENRES), size=40))
    second_sample = closure(random_generator.dirichlet(np.ones(N_GENRES), size=40))
    perturbing_composition = closure(random_generator.dirichlet(np.ones(N_GENRES)))

    assert np.allclose(
        aitchison_distance(
            perturbation(first_sample, perturbing_composition),
            perturbation(second_sample, perturbing_composition),
        ),
        aitchison_distance(first_sample, second_sample),
        atol=NUMERIC_TOLERANCE,
    )


def test_distancia_escala_con_powering(random_generator):
    first_composition = closure(random_generator.dirichlet(np.ones(N_GENRES)))
    second_composition = closure(random_generator.dirichlet(np.ones(N_GENRES)))
    scaling_exponent = 2.5

    assert np.isclose(
        aitchison_distance(
            powering(scaling_exponent, first_composition),
            powering(scaling_exponent, second_composition),
        ),
        scaling_exponent * aitchison_distance(first_composition, second_composition),
        atol=NUMERIC_TOLERANCE,
    )


def test_distancia_cumple_la_desigualdad_triangular(random_generator):
    first_composition = closure(random_generator.dirichlet(np.ones(N_GENRES)))
    second_composition = closure(random_generator.dirichlet(np.ones(N_GENRES)))
    third_composition = closure(random_generator.dirichlet(np.ones(N_GENRES)))

    direct_distance = aitchison_distance(first_composition, third_composition)
    distance_through_second = aitchison_distance(first_composition, second_composition) + aitchison_distance(second_composition, third_composition)

    assert direct_distance <= distance_through_second + NUMERIC_TOLERANCE


def test_variacion_es_simetrica_con_diagonal_nula(composition_sample):
    variation = variation_matrix(composition_sample)

    assert variation.shape == (N_GENRES, N_GENRES)
    assert np.allclose(variation, variation.T, atol=NUMERIC_TOLERANCE)
    assert np.allclose(np.diag(variation), 0.0, atol=NUMERIC_TOLERANCE)


def test_variacion_es_no_negativa(composition_sample):
    assert np.all(variation_matrix(composition_sample) >= -NUMERIC_TOLERANCE)


def test_variacion_es_nula_entre_partes_proporcionales(random_generator):
    sample_with_proportional_pair = random_generator.uniform(0.1, 1.0, size=(60, N_GENRES))
    sample_with_proportional_pair[:, 1] = sample_with_proportional_pair[:, 0] * 3.0

    variation = variation_matrix(closure(sample_with_proportional_pair))

    assert np.isclose(variation[0, 1], 0.0, atol=NUMERIC_TOLERANCE)


def test_variacion_es_invariante_ante_perturbacion(composition_sample, random_generator):
    perturbing_composition = closure(random_generator.dirichlet(np.ones(N_GENRES)))

    assert np.allclose(
        variation_matrix(perturbation(composition_sample, perturbing_composition)),
        variation_matrix(composition_sample),
        atol=NUMERIC_TOLERANCE,
    )
