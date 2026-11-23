"""Small, dependency-free provenance checks used by the P2 audit suite."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable


def static_provenance_violations(paths: Iterable[str | Path]) -> list[str]:
    """Return feature modules that import scenario/label sources."""
    violations: list[str] = []
    forbidden = ("scenario_injector", "dataset_generator", "scenario_registry")
    for raw in paths:
        path = Path(raw)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if any(token in name for token in forbidden):
                    violations.append(f"{path}: {name}")
    return violations


def compare_feature_dicts(left: dict, right: dict, *, timing_tolerance: float = 1e-3) -> dict:
    """Compare serialized feature dictionaries while allowing timing jitter."""
    timing = {"nbd_mean_response_time_ms", "nbd_std_response_time_ms"}
    keys_equal = set(left) == set(right)
    differences: dict[str, dict[str, float]] = {}
    for key in sorted(set(left) | set(right)):
        if key not in left or key not in right:
            differences[key] = {"left": left.get(key), "right": right.get(key)}
            continue
        try:
            delta = abs(float(left[key]) - float(right[key]))
        except (TypeError, ValueError):
            delta = 0.0 if left[key] == right[key] else float("inf")
        if delta > timing_tolerance or key not in timing:
            if left[key] != right[key]:
                differences[key] = {"left": left[key], "right": right[key]}
    return {"keys_equal": keys_equal, "differences": differences, "passed": not differences and keys_equal}
