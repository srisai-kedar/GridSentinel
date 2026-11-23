from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.baselines import classical_scores, guard_training_path


def test_training_guard_rejects_heldout_filename():
    with pytest.raises(PermissionError):
        guard_training_path(Path("heldout_test.csv"))


def test_classical_scores_are_label_free_and_deterministic():
    frame = pd.DataFrame({"pcd_max_lnr": [2.9, 3.1], "pcd_chi2_failed": [0, 1], "nbd_unexpected_write_count": [0, 2]})
    scores = classical_scores(frame)
    assert np.array_equal(scores["classical_bad_data"], np.array([0.0, 1.0]))
    assert np.array_equal(scores["rule_nbd_unexpected_write"], np.array([0.0, 1.0]))


def test_non_final_p7_scripts_contain_no_literal_heldout_reader():
    for name in ["baselines.py", "generate_baseline_matrix.py"]:
        source = Path(__file__).resolve().parents[1] / "scripts" / name
        assert "test" not in source.read_text(encoding="utf-8").lower()
