import numpy as np


def closure(raw_parts):
    raw_parts = np.asarray(raw_parts, dtype=float)

    if np.any(raw_parts <= 0):
        raise ValueError("closure() requiere partes estrictamente positivas. Los ceros se tratan antes con reemplazo multiplicativo bayesiano.")

    total_per_composition = raw_parts.sum(axis=-1, keepdims=True)
    return raw_parts / total_per_composition


def geometric_mean(compositions):
    compositions = np.asarray(compositions, dtype=float)

    log_parts = np.log(compositions)

    if compositions.ndim == 1:
        return float(np.exp(np.mean(log_parts)))
    return np.exp(np.mean(log_parts, axis=-1, keepdims=True))


def center(compositions_sample):
    mean_clr_coordinates = np.mean(clr(compositions_sample), axis=0)
    return clr_inv(mean_clr_coordinates)


def perturbation(composition, perturbing_composition):
    return closure(np.asarray(composition, dtype=float) * np.asarray(perturbing_composition, dtype=float))


def powering(exponent, composition):
    return closure(np.asarray(composition, dtype=float) ** float(exponent))


def clr(compositions):
    closed_parts = closure(compositions)

    return np.log(closed_parts) - np.log(geometric_mean(closed_parts))


def clr_inv(clr_coordinates):
    return closure(np.exp(np.asarray(clr_coordinates, dtype=float)))


def ilr_basis_from_sbp(sbp_matrix):
    sbp_matrix = np.asarray(sbp_matrix, dtype=float)
    n_parts, n_balances = sbp_matrix.shape

    if n_balances != n_parts - 1:
        raise ValueError(f"Una SBP sobre {n_parts} partes necesita exactamente {n_parts - 1} balances; se recibieron {n_balances}.")
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
            raise ValueError(f"El balance {balance_index} no parte el conjunto en dos grupos no vacíos: falta al menos un +1 o un -1.")

        n_parts_in_balance = n_numerator_parts + n_denominator_parts

        orthonormal_basis[is_numerator_part, balance_index] = np.sqrt(n_denominator_parts / (n_numerator_parts * n_parts_in_balance))
        orthonormal_basis[is_denominator_part, balance_index] = -np.sqrt(n_numerator_parts / (n_denominator_parts * n_parts_in_balance))

    return orthonormal_basis


def ilr(compositions, orthonormal_basis):
    return clr(compositions) @ np.asarray(orthonormal_basis, dtype=float)


def ilr_inv(ilr_coordinates, orthonormal_basis):
    orthonormal_basis = np.asarray(orthonormal_basis, dtype=float)
    reconstructed_clr = np.asarray(ilr_coordinates, dtype=float) @ orthonormal_basis.T
    return clr_inv(reconstructed_clr)


def aitchison_distance(first_composition, second_composition):
    clr_difference = clr(first_composition) - clr(second_composition)
    return np.sqrt(np.sum(clr_difference**2, axis=-1))


def variation_matrix(compositions_sample, ddof=1):
    log_transformed_parts = np.log(closure(compositions_sample))

    pairwise_log_ratios = log_transformed_parts[:, :, None] - log_transformed_parts[:, None, :]

    return np.var(pairwise_log_ratios, axis=0, ddof=ddof)


GENRES = ("ROCK", "TROP", "FOLK", "TANG", "JAZZ", "ELEC", "CLAS", "OTRO")

SBP_GENRES = np.array(
    [
        [-1, 0, -1, 0, -1, 0, 1],
        [-1, 0, 1, 1, 0, 0, 0],
        [1, -1, 0, 0, 0, 0, 0],
        [1, 1, 0, 0, 0, 0, 0],
        [-1, 0, -1, 0, 1, 1, 0],
        [-1, 0, 1, -1, 0, 0, 0],
        [-1, 0, -1, 0, 1, -1, 0],
        [-1, 0, -1, 0, -1, 0, -1],
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
    return ilr_basis_from_sbp(SBP_GENRES)
