from __future__ import annotations

import numpy as np

from scripts.expo.p10_frontier import make_state_vector, scaled_attack


def test_state_direction_is_deterministic_and_normalised():
    first = make_state_vector("exact_current_operating_point", "single_rtu", 1010)
    second = make_state_vector("exact_current_operating_point", "single_rtu", 9999)
    assert np.array_equal(first, second)
    assert np.isclose(np.linalg.norm(first), 1.0)


def test_two_rtu_direction_has_two_nonzero_rtu_blocks():
    vector = make_state_vector("exact_current_operating_point", "two_rtu_coordinated", 1010)
    assert np.count_nonzero(vector[:6]) == 2
    assert np.count_nonzero(vector[6:]) == 2


def test_scaled_attack_has_requested_whitened_norm_and_can_be_restricted():
    matrix = np.eye(4)
    mapping = np.arange(4)
    sigma = np.ones(4)
    full = scaled_attack(matrix, np.ones(4), mapping, sigma, [0, 1], 3.0, restrict=False)
    restricted = scaled_attack(matrix, np.ones(4), mapping, sigma, [0, 1], 3.0, restrict=True)
    assert np.isclose(np.linalg.norm(full), 3.0)
    assert np.isclose(np.linalg.norm(restricted), 3.0)
    assert np.array_equal(restricted[2:], np.zeros(2))
