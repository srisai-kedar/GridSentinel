import pandas as pd

from scripts.expo.p1_attribution_diagnostic import attack_recall, legacy_measurement_matches_rtu, subtype_recall


def test_legacy_mapping_is_explicit_and_distinct_from_corrected_line_ownership():
    assert legacy_measurement_matches_rtu("line", 0, 1)
    assert not legacy_measurement_matches_rtu("line", 0, 2)


def test_subtype_recall_is_computed_from_labels_and_predictions():
    frame = pd.DataFrame({
        "top_level_label": ["Cyber Intrusion", "Cyber Intrusion", "Normal"],
        "subtype_label": ["data_injection", "replay", "normal"],
    })
    result = subtype_recall(frame, pd.Series([True, False, False]).to_numpy())
    assert result["data_injection"] == {"support": 1, "recall": 1.0}
    assert result["replay"] == {"support": 1, "recall": 0.0}


def test_attack_recall_is_null_when_no_attack_rows_exist():
    frame = pd.DataFrame({"top_level_label": ["Normal"]})
    assert attack_recall(frame, pd.Series([False]).to_numpy()) is None
