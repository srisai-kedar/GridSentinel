"""Two-level clustered bootstrap and Holm correction."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Iterable, Mapping

import numpy as np


def cluster_bootstrap(
    runs: Mapping[str, Iterable[Any]],
    statistic: Callable[[list[Any]], float],
    *,
    replicates: int = 10000,
    seed: int = 0,
) -> dict[str, Any]:
    """Resample runs, then observations/episodes within each selected run."""
    if replicates <= 0:
        raise ValueError("replicates must be positive")
    run_items = {str(key): list(value) for key, value in runs.items()}
    if not run_items or any(not values for values in run_items.values()):
        raise ValueError("runs must be non-empty and each run must contain observations")
    names = list(run_items)
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(replicates):
        sampled_runs = rng.choice(names, size=len(names), replace=True)
        sample = []
        for name in sampled_runs:
            members = run_items[str(name)]
            sample.extend(members[int(index)] for index in rng.integers(0, len(members), size=len(members)))
        values.append(float(statistic(sample)))
    values.sort()
    return {
        "replicates": replicates,
        "seed": seed,
        "estimate": float(statistic([item for values in run_items.values() for item in values])),
        "interval_95": [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))],
    }


def holm_adjust(p_values: Mapping[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p-values."""
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for index, (name, p_value) in enumerate(ordered):
        candidate = min(1.0, (total - index) * float(p_value))
        running = max(running, candidate)
        adjusted[name] = running
    return adjusted
