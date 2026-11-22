"""Describe generated P3 datasets without training, tuning, or selection."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def summarize_frame(frame: pd.DataFrame, name: str) -> dict[str, Any]:
    result: dict[str, Any] = {"split": name, "rows": int(len(frame)), "columns": list(frame.columns)}
    result["class_counts"] = {str(k): int(v) for k, v in frame["top_level_label"].value_counts().sort_index().items()}
    result["class_shares"] = {str(k): float(v) for k, v in frame["top_level_label"].value_counts(normalize=True).sort_index().items()}
    result["subtype_counts"] = {str(k): int(v) for k, v in frame["subtype_label"].value_counts().sort_index().items()}
    result["episode_counts_by_type"] = {
        str(k): int(v) for k, v in frame.groupby("scenario_type")["episode_id"].nunique().sort_index().items()
    }
    tick_frame = frame[["tick", "scenario_type"]].drop_duplicates()
    result["time_shares_by_scenario"] = {
        str(k): float(v) for k, v in tick_frame["scenario_type"].value_counts(normalize=True).sort_index().items()
    }
    evidence = frame.groupby("scenario_type")["evidence_visible"].mean().sort_index()
    result["evidence_visible_fraction_by_scenario"] = {str(k): float(v) for k, v in evidence.items()}
    result["attack_active_rows"] = int(frame["attack_active"].sum())
    result["missing_counts"] = {str(k): int(v) for k, v in frame.isna().sum().items() if int(v)}
    return result


def parse_split(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise ValueError("split must be NAME=PATH")
    name, path = value.split("=", 1)
    if not name or not path:
        raise ValueError("split must be NAME=PATH")
    return name, Path(path)


def describe(splits: list[tuple[str, Path]], out_dir: Path, argv: list[str]) -> dict[str, Any]:
    summaries = []
    input_hashes = {}
    for name, path in splits:
        frame = pd.read_csv(path)
        summaries.append(summarize_frame(frame, name))
        input_hashes[str(path)] = sha256(path)
    result = {"task_id": "P3", "splits": summaries}
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "dataset_description.json"
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    lines = ["# P3 Dataset Description", ""]
    for item in summaries:
        lines.extend([
            f"## {item['split']}", "",
            f"- Rows: `{item['rows']}`",
            f"- Class counts: `{json.dumps(item['class_counts'], sort_keys=True)}`",
            f"- Class shares: `{json.dumps(item['class_shares'], sort_keys=True)}`",
            f"- Episode counts by type: `{json.dumps(item['episode_counts_by_type'], sort_keys=True)}`",
            f"- Time shares by scenario: `{json.dumps(item['time_shares_by_scenario'], sort_keys=True)}`",
            f"- Evidence-visible fractions: `{json.dumps(item['evidence_visible_fraction_by_scenario'], sort_keys=True)}`",
            f"- Attack-active rows: `{item['attack_active_rows']}`",
            "",
        ])
    md_path = out_dir / "dataset_description.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    try:
        git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        git_sha = "unknown"
    manifest = {
        "task_id": "P3",
        "git_sha": git_sha,
        "python_version": platform.python_version(),
        "cpu_model": platform.processor() or platform.machine(),
        "cli_arguments": argv,
        "seeds": {},
        "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ended_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "input_datasets": input_hashes,
        "output_datasets": {str(path): sha256(path) for path in [json_path, md_path]},
    }
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", action="append", required=True, help="NAME=CSV path; repeat per split")
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    result = describe([parse_split(item) for item in args.split], args.out_dir, list(__import__("sys").argv))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
