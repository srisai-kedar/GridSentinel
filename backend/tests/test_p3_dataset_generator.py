import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1] / "app"))
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "expo"))

from app.ml.dataset_generator import resolve_prevalence_regime
from describe_dataset import summarize_frame


def test_operational_regime_has_documented_low_prevalence():
    probabilities = resolve_prevalence_regime("operational")
    assert probabilities == {
        "normal": 0.97,
        "natural_fault": 0.01,
        "sensor_malfunction": 0.01,
        "cyber": 0.01,
    }


def test_clean_regime_excludes_cyber_and_sensor_classes():
    probabilities = resolve_prevalence_regime("clean")
    assert probabilities == {"normal": 0.5, "natural_fault": 0.5}


def test_dataset_description_counts_episodes_and_evidence():
    frame = pd.DataFrame(
        {
            "top_level_label": ["Normal", "Cyber Intrusion", "Cyber Intrusion"],
            "subtype_label": ["normal", "replay", "replay"],
            "scenario_type": ["Normal", "Cyber Intrusion", "Cyber Intrusion"],
            "episode_id": ["r:1", "r:2", "r:2"],
            "tick": [1, 2, 3],
            "evidence_visible": [False, False, True],
            "attack_active": [False, True, True],
        }
    )
    result = summarize_frame(frame, "validation")
    assert result["rows"] == 3
    assert result["episode_counts_by_type"] == {"Cyber Intrusion": 1, "Normal": 1}
    assert result["evidence_visible_fraction_by_scenario"]["Cyber Intrusion"] == 0.5
