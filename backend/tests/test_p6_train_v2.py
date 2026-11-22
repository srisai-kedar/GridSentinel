from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.expo.train_v2 import add_staleness_features, ece, feature_arms, policy_frame, threshold_for_validation


def sample_frame():
    return pd.DataFrame({
        "run_id": ["a", "a", "a", "b"], "rtu_id": [1, 1, 1, 1], "tick": [0, 1, 2, 0],
        "pcd_voltage_pu_reported": [1.0, 1.0, 1.1, 1.0], "pcd_p_mw_reported": [1.0, 1.0, 1.0, 1.0], "pcd_temporal_dq_dt_3tick": [0.0, 0.0, 0.2, 0.0],
        "attack_active": [False, True, True, False], "evidence_visible": [False, True, False, False], "episode_id": ["n", "e", "e", "n2"],
    })


def test_staleness_uses_same_rtu_run_history():
    out = add_staleness_features(sample_frame())
    assert out.loc[1, "stale_register_run_length"] == 2
    assert out.loc[2, "stale_register_run_length"] == 1


def test_evidence_policy_drops_invisible_attack_from_training():
    frame, y = policy_frame(sample_frame(), "evidence_visible", True)
    assert len(frame) == 3
    assert y.tolist() == [0, 1, 0]


def test_feature_arms_have_expected_partitions():
    arms = feature_arms()
    assert len(arms["base28"]) == 28
    assert len(arms["full37"]) == 37
    assert set(arms["nbd_only"]).isdisjoint(set(arms["pcd_only"]))


def test_validation_threshold_obeys_one_percent_normal_fpr():
    frame = sample_frame()
    score = np.array([0.01, 0.9, 0.8, 0.02])
    threshold, details = threshold_for_validation(frame, score, "attack_active")
    assert threshold >= 0.8
    assert details["fpr"] <= 0.01


def test_ece_is_zero_for_perfectly_calibrated_bins():
    assert ece(np.array([0, 1]), np.array([0.0, 1.0])) == 0.0
