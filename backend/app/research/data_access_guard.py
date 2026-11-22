"""Guards preventing non-final research scripts from reading test datasets."""

from __future__ import annotations

import ast
import datetime as _datetime
import hashlib
import json
from pathlib import Path
from typing import Iterable


def guard_dataset_path(path: str | Path, *, purpose: str, allow_test: bool = False) -> Path:
    """Reject paths containing ``test`` unless the final evaluator explicitly opts in."""
    resolved = Path(path)
    if "test" in resolved.name.lower() and not allow_test:
        raise PermissionError(
            f"Test-set lock: {purpose} may not read a dataset path matching *test*: {resolved}"
        )
    return resolved


def append_test_access_log(path: str | Path, *, script: str, purpose: str) -> None:
    """Append a reproducible access record for the only test-reading entry point."""
    source = Path(path)
    record = {
        "timestamp_utc": _datetime.datetime.now(_datetime.timezone.utc).isoformat(),
        "script": script,
        "purpose": purpose,
        "path": str(source.resolve()),
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }
    log_path = Path("backend/reports/research/test_access_log.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def assert_no_literal_test_reads(paths: Iterable[str | Path]) -> None:
    """Static scan: reject literal test-dataset paths in data-reading calls."""
    reader_names = {"open", "read_csv", "read_text", "read_bytes", "read_parquet"}
    for source_path in paths:
        source = Path(source_path)
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name not in reader_names:
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and "test" in arg.value.lower():
                    raise AssertionError(f"Static test-set read in {source}: {arg.value}")
