"""Run isolated generator processes concurrently for the P0 smoke test."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ROOT = ROOT / "backend" / "experiments" / "P0" / "concurrency"
REPORT_ROOT = ROOT / "backend" / "reports" / "research" / "P0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks", type=int, default=40)
    parser.add_argument("--seeds", nargs="+", type=int, default=[101, 202, 303, 404])
    parser.add_argument("--port-base", type=int, default=15021)
    parser.add_argument("--port-step", type=int, default=1000)
    args = parser.parse_args()
    EXPERIMENT_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    processes = []
    started = time.perf_counter()
    for index, seed in enumerate(args.seeds):
        run_dir = EXPERIMENT_ROOT / f"seed_{seed}"
        output = run_dir / "generated.csv"
        command = [
            sys.executable,
            "-m",
            "app.ml.dataset_generator",
            "--seed", str(seed), "--ticks", str(args.ticks),
            "--mode", "scenario_mix", "--port-base", str(args.port_base + index * args.port_step),
            "--run-id", f"concurrency-{seed}", "--out", str(output),
        ]
        processes.append({"seed": seed, "port_base": args.port_base + index * args.port_step,
                          "command": command, "process": subprocess.Popen(command, cwd=ROOT / "backend", text=True,
                                                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)})
    results = []
    for item in processes:
        stdout, stderr = item["process"].communicate()
        run_dir = EXPERIMENT_ROOT / f"seed_{item['seed']}"
        manifest_path = run_dir / "run_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
        results.append({"seed": item["seed"], "port_base": item["port_base"], "returncode": item["process"].returncode,
                        "manifest": manifest, "stdout": stdout[-2000:], "stderr": stderr[-2000:]})
    report = {"task_id": "P0", "ticks": args.ticks, "requested_runs": len(args.seeds),
              "elapsed_seconds": round(time.perf_counter() - started, 6), "runs": results}
    report_path = REPORT_ROOT / "concurrency_smoke.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    with (REPORT_ROOT / "throughput.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["seed", "port_base", "returncode", "rows", "throughput_ticks_per_second"])
        writer.writeheader()
        for item in results:
            manifest = item["manifest"] or {}
            writer.writerow({"seed": item["seed"], "port_base": item["port_base"], "returncode": item["returncode"],
                             "rows": manifest.get("rows", ""), "throughput_ticks_per_second": manifest.get("throughput_ticks_per_second", "")})
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if all(item["returncode"] == 0 and item["manifest"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
