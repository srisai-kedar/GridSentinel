from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.expo.p8_alert_layers import cusum_alerts, persistence_alerts, choose_for_budget


def _frame():
    return pd.DataFrame([
        {"run_id": "r", "rtu_id": 1, "tick": 0, "is_clean_run": False, "duration_hours": 1.0, "episode_id": "e", "scenario_type": "fdi", "attack_active": True, "evidence_visible": True},
        {"run_id": "r", "rtu_id": 1, "tick": 1, "is_clean_run": False, "duration_hours": 1.0, "episode_id": "e", "scenario_type": "fdi", "attack_active": True, "evidence_visible": True},
        {"run_id": "r", "rtu_id": 1, "tick": 2, "is_clean_run": False, "duration_hours": 1.0, "episode_id": "e", "scenario_type": "fdi", "attack_active": True, "evidence_visible": True},
        {"run_id": "r", "rtu_id": 2, "tick": 0, "is_clean_run": True, "duration_hours": 1.0, "episode_id": None, "scenario_type": "normal", "attack_active": False, "evidence_visible": False},
    ])


def test_persistence_requires_k_of_n_and_respects_cooldown():
    frame = _frame()
    alerts = persistence_alerts(frame, np.asarray([0.9, 0.1, 0.1, 0.0]), 0.5, 2, 3, 1)
    assert alerts.tolist() == [False, False, False, False]
    alerts = persistence_alerts(frame, np.asarray([0.9, 0.9, 0.9, 0.0]), 0.5, 2, 3, 1)
    assert alerts[2]


def test_cusum_accumulates_excess_score():
    frame = _frame()
    alerts = cusum_alerts(frame, np.asarray([0.7, 0.7, 0.7, 0.0]), 0.5, 0.0, 0.3, 0)
    assert alerts[1]


def test_budget_selection_returns_highest_episode_recall_eligible_candidate():
    candidates = [
        {"metrics": {"episode": {"recall": 0.5}, "false_alarms": {"per_hour": 1.0}}, "parameters": {"threshold": 0.5}},
        {"metrics": {"episode": {"recall": 1.0}, "false_alarms": {"per_hour": 1.0}}, "parameters": {"threshold": 0.7}},
        {"metrics": {"episode": {"recall": 1.0}, "false_alarms": {"per_hour": 2.0}}, "parameters": {"threshold": 0.9}},
    ]
    selected = choose_for_budget(candidates, 1.0)
    assert selected["parameters"]["threshold"] == 0.7
