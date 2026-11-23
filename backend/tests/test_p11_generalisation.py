from __future__ import annotations

from pathlib import Path

import pytest

from scripts.expo.p11_generalisation import REDUNDANCY_MEASUREMENT_COUNTS, reject_heldout_path


def test_redundancy_sweep_is_monotone_and_reaches_observability_boundary():
    assert REDUNDANCY_MEASUREMENT_COUNTS == tuple(sorted(REDUNDANCY_MEASUREMENT_COUNTS, reverse=True))
    assert REDUNDANCY_MEASUREMENT_COUNTS[-1] == 13


def test_p11_runtime_guard_rejects_heldout_paths():
    with pytest.raises(RuntimeError):
        reject_heldout_path(Path("backend/experiments/ood_test_seed400.csv"))


def test_p11_runtime_guard_accepts_training_path():
    path = Path("backend/experiments/P6-complete/generated/train_seed100.csv")
    assert reject_heldout_path(path) == path
