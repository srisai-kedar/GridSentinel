from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.baselines import guard_training_path, select_threshold


def test_training_guard_rejects_heldout_filename():
    with pytest.raises(PermissionError):
        guard_training_path(Path("heldout_test.csv"))


def test_training_reader_does_not_accept_heldout_filename():
    guard_training_path(Path("heldout_seed300.csv"))


def test_threshold_selection_uses_only_passed_validation_rows():
    rows = pd.DataFrame([
        {"run_id": "clean", "tick": 0, "rtu_id": 1, "episode_id": None, "scenario_type": "normal", "attack_active": False, "evidence_visible": False, "is_clean_run": True, "duration_hours": 1.0},
        {"run_id": "attack", "tick": 0, "rtu_id": 1, "episode_id": "episode-1", "scenario_type": "fdi", "attack_active": True, "evidence_visible": True, "is_clean_run": False, "duration_hours": 1.0},
    ])
    threshold, result = select_threshold(rows, np.asarray([0.1, 0.9]))
    assert threshold == 0.9
    assert result["episode"]["recall"] == 1.0


def test_non_final_p7_scripts_contain_no_literal_heldout_reader():
    for name in ["baselines.py", "generate_p7_data.py"]:
        source = Path(__file__).resolve().parents[1] / "scripts" / name
        assert "test" not in source.read_text(encoding="utf-8").lower()
