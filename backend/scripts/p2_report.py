"""Helpers for parsing machine-generated test summaries for research reports."""
from __future__ import annotations

import re
from pathlib import Path


def parse_pytest_counts(path: str | Path) -> dict[str, int | str]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    match = re.search(r"(?:(\d+) failed, )?(?:(\d+) passed)(?:, (\d+) warnings)?", text)
    if not match:
        raise ValueError(f"pytest summary not found in {path}")
    failed, passed, warnings = match.groups()
    return {"failed": int(failed or 0), "passed": int(passed), "warnings": int(warnings or 0), "raw_summary": match.group(0)}
