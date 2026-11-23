"""Generate capture-aware P7 data without reading the held-out outputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path("experiments/P7-complete"))
    parser.add_argument("--ticks", type=int, default=10)
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    out = args.out_dir.resolve()
    generated = out / "generated"
    if any(generated.glob("*.csv")):
        raise FileExistsError(f"refusing to overwrite existing P7 data: {generated}")
    generated.mkdir(parents=True, exist_ok=True)
    plans = []
    plans += [("train", seed, "scenario_mix", "stress") for seed in range(100, 110)]
    plans += [("validation", seed, "scenario_mix", "operational") for seed in range(200, 203)]
    plans += [("clean_train", seed, "clean", "clean") for seed in range(500, 503)]
    plans += [("clean_validation", seed, "clean", "clean") for seed in range(503, 505)]
    plans += [("heldout", seed, "scenario_mix", "stress") for seed in range(300, 305)]
    produced = []
    for index, (split, seed, mode, regime) in enumerate(plans):
        output = generated / f"{split}_seed{seed}.csv"
        command = [sys.executable, "-m", "app.ml.dataset_generator", "--seed", str(seed), "--ticks", str(args.ticks), "--out", str(output), "--run-id", f"P7-{split}-{seed}", "--port-base", str(16000 + index * 20), "--mode", mode, "--regime", regime]
        subprocess.run(command, cwd=ROOT, check=True)
        produced.append(output)
    manifest = {
        "task_id": "P7",
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT.parent, text=True).strip(),
        "python_version": sys.version,
        "cpu_model": platform.processor() or platform.machine(),
        "cli_arguments": {key: str(value) for key, value in vars(args).items()},
        "seeds": {split: [seed for planned_split, seed, _, _ in plans if planned_split == split] for split in sorted({item[0] for item in plans})},
        "started_at_utc": started.isoformat(),
        "ended_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_datasets": {},
        "output_datasets": {str(path): digest(path) for path in produced},
    }
    (out / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
