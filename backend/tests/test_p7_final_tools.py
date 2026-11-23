from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from eval_final import _paired_cluster_bootstrap


def _episode(run, episode, detected):
    return {"run_id": run, "episode_id": episode, "detected": detected}


def test_paired_cluster_bootstrap_recovers_identical_methods():
    result = {"episode_results": [_episode("r1", "e1", True), _episode("r2", "e2", False)]}
    comparison = _paired_cluster_bootstrap(result, result, seed=1, reps=20)
    assert comparison["episodes"] == 2
    assert comparison["difference_mean"] == 0.0
    assert comparison["ci95"] == [0.0, 0.0]
