from app.ml.dataset_generator import resolve_scenario_probabilities


def test_clean_mode_excludes_attack_probabilities():
    probabilities = resolve_scenario_probabilities(
        "clean", {"normal": 0.2, "natural_fault": 0.3, "sensor_malfunction": 0.4, "cyber": 0.1}
    )
    assert probabilities == {"normal": 0.4, "natural_fault": 0.6}


def test_default_mix_is_normalized():
    probabilities = resolve_scenario_probabilities("scenario_mix")
    assert sum(probabilities.values()) == 1.0
    assert set(probabilities) == {"normal", "natural_fault", "sensor_malfunction", "cyber"}


def test_negative_probability_is_rejected():
    try:
        resolve_scenario_probabilities("scenario_mix", {"normal": -1.0})
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:
        raise AssertionError("negative probability was accepted")
