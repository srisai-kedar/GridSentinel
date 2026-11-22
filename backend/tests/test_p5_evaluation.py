from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[2]))

from eval.bootstrap import cluster_bootstrap, holm_adjust
from eval.metrics import evaluate, poisson_interval
from app.research.data_access_guard import assert_no_literal_test_reads, guard_dataset_path


def synthetic_rows(alert_episode_ids=("ep1",), false_alarm=False):
    rows = []
    for tick in range(1, 11):
        attack = 3 <= tick <= 5
        alert = attack and ("ep1" in alert_episode_ids) or (false_alarm and tick == 8)
        rows.append({
            "run_id": "run1", "tick": tick, "rtu_id": 1,
            "episode_id": "ep1" if attack else None,
            "scenario_type": "FDI" if attack else "Normal",
            "attack_active": attack, "evidence_visible": attack,
            "alert": alert,
        })
    return rows


def test_metrics_recover_reading_tick_episode_and_alarm_counts():
    result = evaluate(synthetic_rows(false_alarm=True), clean_runs={"run1": 1.0}, gap=0, tail=0, grace=0)
    assert result["reading"] == {"rows": 10, "alerts": 4, "attack_rows": 3, "non_attack_rows": 7}
    assert result["evidence_visible"] == {"rows": 3, "alerts": 3}
    assert result["tick"]["recall"] == 1.0
    assert result["episode"]["recall"] == 1.0
    assert result["alert_events"]["false"] == 1
    assert result["false_alarms"]["per_hour"] == 1.0


def test_poisson_interval_and_gap_tail_are_defined():
    interval = poisson_interval(0, 1.0)
    assert interval[0] == 0.0 and interval[1] > 0.0
    rows = synthetic_rows(false_alarm=True)
    result = evaluate(rows, clean_runs={"run1": 1.0}, gap=2, tail=2, grace=1)
    assert result["configuration"] == {"gap": 2, "tail": 2, "grace": 1}


def test_cluster_bootstrap_returns_interval_covering_known_mean():
    runs = {f"run{i}": [0.5] * 8 for i in range(8)}
    result = cluster_bootstrap(runs, lambda sample: float(np.mean(sample)), replicates=200, seed=17)
    assert result["estimate"] == 0.5
    assert result["interval_95"] == [0.5, 0.5]


def test_bootstrap_coverage_is_in_expected_range_for_200_replicates():
    rng = np.random.default_rng(91)
    covered = 0
    true_mean = 0.6
    for _ in range(200):
        runs = {f"run{i}": list(rng.binomial(1, true_mean, size=12)) for i in range(10)}
        interval = cluster_bootstrap(runs, lambda sample: float(np.mean(sample)), replicates=250, seed=int(rng.integers(1_000_000)))["interval_95"]
        covered += int(interval[0] <= true_mean <= interval[1])
    assert 180 <= covered <= 198


def test_holm_adjustment_is_monotonic():
    adjusted = holm_adjust({"a": 0.01, "b": 0.02, "c": 0.8})
    assert adjusted["a"] <= adjusted["b"] <= adjusted["c"] <= 1.0


def test_test_set_lock_rejects_runtime_and_scans_non_final_scripts(tmp_path):
    test_path = tmp_path / "heldout_test.csv"
    test_path.write_text("x\n1\n", encoding="utf-8")
    try:
        guard_dataset_path(test_path, purpose="P5 training")
    except PermissionError:
        pass
    else:
        raise AssertionError("runtime test-set guard accepted a test path")
    assert_no_literal_test_reads([Path(__file__).parents[2] / "eval" / "metrics.py", Path(__file__).parents[2] / "eval" / "bootstrap.py"])
