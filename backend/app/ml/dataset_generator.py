"""
dataset_generator.py
--------------------
Programmatically runs the GridSentinel simulation across randomized cyber-physical
scenarios, extracts feature vectors per RTU per tick, and saves balanced labeled CSVs.

Labels generated:
  - top_level_label: "Normal" | "Natural Fault" | "Cyber Intrusion"
  - subtype_label: "normal" | "line_trip" | "short_circuit" | "data_injection" | "command_injection" | "replay"
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import datetime
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import random
import subprocess
import time
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from app.core.feeder import build_feeder
from app.ml.feature_engineering import FEATURE_SCHEMA, extract_features
from app.core.topology_map import measurement_matches_rtu
from app.ot.rtu_server import configure_port_base, rtu_pool
from app.ot.scenario_injector import scenario_injector
from app.ot.simulation_loop import sim_loop
from app.ot.traffic_logger import traffic_logger


async def generate_dataset(
    seed: int = 42,
    total_ticks: int = 2000,
    out_csv: Optional[str] = None,
    mode: str = "scenario_mix",
    port_base: int = 5021,
    run_id: str = "default",
    scenario_probabilities: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """
    Run automated simulation loop for `total_ticks` and record labeled dataset.

    Parameters
    ----------
    seed : int
        RNG seed for reproducibility
    total_ticks : int
        Number of simulation ticks to run
    out_csv : str, optional
        Path to save CSV output

    Returns
    -------
    pd.DataFrame
        DataFrame containing all feature columns plus labels.
    """
    if mode not in {"scenario_mix", "clean"}:
        raise ValueError(f"Unsupported generation mode: {mode}")
    probabilities = resolve_scenario_probabilities(mode, scenario_probabilities)
    configure_port_base(port_base)
    started = datetime.datetime.now(datetime.timezone.utc)
    perf_started = time.perf_counter()
    print(f"[DatasetGenerator] Starting generation: Seed={seed}, Ticks={total_ticks}, Mode={mode}, Run={run_id}...")
    random.seed(seed)
    np.random.seed(seed)

    # Ensure clean logger and network
    traffic_logger.clear()
    net = build_feeder()
    await sim_loop.start(net=net)

    records: List[Dict[str, Any]] = []

    # Scenario scheduling probabilities
    # We balance transitions between Normal, Fault, and Attacks
    current_scenario_type = "Normal"
    current_subtype = "normal"
    scenario_remaining_ticks = 0
    attack_target_rtu = 1

    telemetry_history: collections.deque = collections.deque(maxlen=3)
    residual_history: collections.deque = collections.deque(maxlen=6)

    try:
        for tick_idx in range(1, total_ticks + 1):
            # Check if we need to transition to a new scenario
            if scenario_remaining_ticks <= 0:
                scenario_injector.clear_all_scenarios(net=net)

                # Pick the next scenario from the configured, normalized probabilities.
                p = random.random()
                normal_cutoff = probabilities.get("normal", 0.0)
                natural_cutoff = normal_cutoff + probabilities.get("natural_fault", 0.0)
                sensor_cutoff = natural_cutoff + probabilities.get("sensor_malfunction", 0.0)
                if p < normal_cutoff:
                    current_scenario_type = "Normal"
                    current_subtype = "normal"
                    scenario_remaining_ticks = random.randint(8, 20)
                elif p < natural_cutoff:
                    current_scenario_type = "Natural Fault"
                    current_subtype = random.choice(["line_trip", "short_circuit"])
                    scenario_remaining_ticks = random.randint(4, 10)

                    if current_subtype == "line_trip":
                        target_line = random.choice([0, 1, 2, 3])
                        scenario_injector.trigger_line_trip(net=net, line_index=target_line)
                    elif current_subtype == "short_circuit":
                        target_bus = random.choice([2, 3, 4, 5])
                        scenario_injector.trigger_short_circuit_stub(
                            net=net,
                            bus_index=target_bus,
                            fault_load_mw=random.uniform(1.8, 3.2),
                            fault_load_mvar=random.uniform(1.0, 2.0),
                            duration_ticks=scenario_remaining_ticks,
                        )
                elif p < sensor_cutoff:
                    current_scenario_type = "Sensor Malfunction"
                    current_subtype = "sensor_drift"
                    attack_target_rtu = random.choice([1, 2, 3, 4, 5])
                    scenario_remaining_ticks = random.randint(5, 15)
                    drift_val = random.choice([-0.08, -0.06, 0.07, 0.09])
                    scenario_injector.inject_sensor_drift(
                        rtu_id=attack_target_rtu,
                        drift_percent=drift_val,
                        duration_ticks=scenario_remaining_ticks,
                    )
                elif mode == "scenario_mix":
                    current_scenario_type = "Cyber Intrusion"
                    current_subtype = random.choice(["data_injection", "command_injection", "replay"])
                    attack_target_rtu = random.choice([1, 2, 3, 4, 5])
                    scenario_remaining_ticks = random.randint(4, 12)

                    if current_subtype == "data_injection":
                        # Fabricate voltage (either overvoltage 1.08-1.25 or undervoltage 0.75-0.90)
                        fake_v = random.choice([random.uniform(1.08, 1.25), random.uniform(0.75, 0.90)])
                        scenario_injector.inject_silent_data_injection(
                            rtu_id=attack_target_rtu,
                            voltage_pu=fake_v,
                            duration_ticks=scenario_remaining_ticks,
                        )
                    elif current_subtype == "command_injection":
                        # Send unauthorized command write to target RTU
                        fake_raw_val = random.randint(11000, 15000)
                        await scenario_injector.inject_command_write(
                            rtu_id=attack_target_rtu,
                            register_address=0,
                            value=fake_raw_val,
                        )
                    elif current_subtype == "replay":
                        scenario_injector.inject_replay(
                            rtu_id=attack_target_rtu,
                            duration_ticks=scenario_remaining_ticks,
                        )

            # Advance simulation tick
            snap = await sim_loop.tick()
            scenario_remaining_ticks -= 1

            # Extract features for each of the 5 monitored RTUs
            recent_traffic = traffic_logger.get_recent_events(limit=30)
            se_res = snap.get("state_estimation", {})
            polled_t = snap.get("polled_modbus_telemetry", {})
            telemetry_history.append(polled_t)

            # Collect per-RTU standardized residuals for history
            all_resids = se_res.get("all_residuals", [])
            tick_residuals_by_rtu: Dict[int, List[float]] = {i: [] for i in range(1, 6)}
            for r in all_resids:
                elem = int(r.get("element", -1))
                elem_type = str(r.get("element_type", "")).lower()
                norm_r = float(r.get("normalised_residual", 0.0))
                for rid in range(1, 6):
                    if measurement_matches_rtu(elem_type, elem, rid):
                        tick_residuals_by_rtu[rid].append(norm_r)

            for rtu_id in range(1, 6):
                feats = extract_features(
                    traffic_events=recent_traffic,
                    state_estimation_result=se_res,
                    target_rtu_id=rtu_id,
                    polled_telemetry=polled_t,
                    telemetry_history=list(telemetry_history),
                    residual_history=list(residual_history),
                )

                # Determine RTU-specific label
                if current_scenario_type == "Cyber Intrusion":
                    if rtu_id == attack_target_rtu:
                        rtu_top_label = "Cyber Intrusion"
                        rtu_sub_label = current_subtype
                    else:
                        rtu_top_label = "Normal"
                        rtu_sub_label = "normal"
                elif current_scenario_type == "Sensor Malfunction":
                    if rtu_id == attack_target_rtu:
                        rtu_top_label = "Sensor Malfunction"
                        rtu_sub_label = "sensor_drift"
                    else:
                        rtu_top_label = "Normal"
                        rtu_sub_label = "normal"
                elif current_scenario_type == "Natural Fault":
                    rtu_top_label = "Natural Fault"
                    rtu_sub_label = current_subtype
                else:
                    rtu_top_label = "Normal"
                    rtu_sub_label = "normal"

                record = dict(feats)
                record["tick"] = tick_idx
                record["rtu_id"] = rtu_id
                record["top_level_label"] = rtu_top_label
                record["subtype_label"] = rtu_sub_label
                records.append(record)

            residual_history.append(tick_residuals_by_rtu)

            if tick_idx % 200 == 0 or tick_idx == total_ticks:
                print(f"  ... Tick {tick_idx}/{total_ticks} complete ({len(records)} samples generated)")

    finally:
        scenario_injector.clear_all_scenarios(net=net)
        await sim_loop.stop()

    df = pd.DataFrame(records)

    # Print class distribution summary
    print("\n[DatasetGenerator] Class Distribution Summary:")
    print("Top-level counts:\n", df["top_level_label"].value_counts())
    print("\nSubtype counts:\n", df["subtype_label"].value_counts())

    if out_csv:
        out_path = Path(out_csv)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, index=False)
        print(f"[DatasetGenerator] Saved dataset to {out_path} ({len(df)} rows)")
        _write_run_manifest(
            out_path=out_path,
            run_id=run_id,
            seed=seed,
            total_ticks=total_ticks,
            mode=mode,
            port_base=port_base,
            probabilities=probabilities,
            started=started,
            elapsed_seconds=time.perf_counter() - perf_started,
            rows=len(df),
        )

    return df


def resolve_scenario_probabilities(
    mode: str, scenario_probabilities: Optional[Dict[str, float]] = None
) -> Dict[str, float]:
    """Return normalized scenario weights, restricting clean mode to benign classes."""
    probabilities = scenario_probabilities or {
        "normal": 0.25,
        "natural_fault": 0.25,
        "sensor_malfunction": 0.25,
        "cyber": 0.25,
    }
    if mode == "clean":
        probabilities = {
            "normal": float(probabilities.get("normal", 0.5)),
            "natural_fault": float(probabilities.get("natural_fault", 0.5)),
        }
    if any(value < 0 for value in probabilities.values()):
        raise ValueError("Scenario probabilities must be non-negative")
    total_probability = sum(probabilities.values())
    if total_probability <= 0:
        raise ValueError("Scenario probabilities must have a positive sum")
    return {key: value / total_probability for key, value in probabilities.items()}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _package_versions() -> Dict[str, str]:
    names = ["numpy", "pandas", "pandapower", "pymodbus", "scikit-learn", "scipy"]
    return {name: importlib.metadata.version(name) for name in names if _has_distribution(name)}


def _has_distribution(name: str) -> bool:
    try:
        importlib.metadata.version(name)
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


def _write_run_manifest(
    *, out_path: Path, run_id: str, seed: int, total_ticks: int, mode: str,
    port_base: int, probabilities: Dict[str, float], started: datetime.datetime,
    elapsed_seconds: float, rows: int,
) -> None:
    end = datetime.datetime.now(datetime.timezone.utc)
    manifest = {
        "task_id": "P0",
        "run_id": run_id,
        "git_sha": _git_sha(),
        "python_version": platform.python_version(),
        "package_versions": _package_versions(),
        "cpu_model": platform.processor() or platform.machine(),
        "cli_arguments": {
            "seed": seed,
            "ticks": total_ticks,
            "mode": mode,
            "port_base": port_base,
            "run_id": run_id,
            "out": str(out_path),
            "scenario_probabilities": probabilities,
        },
        "seeds": {"python_random": seed, "numpy": seed},
        "started_at_utc": started.isoformat(),
        "ended_at_utc": end.isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 6),
        "throughput_ticks_per_second": round(total_ticks / elapsed_seconds, 6) if elapsed_seconds else None,
        "rows": rows,
        "timing_affected_columns": ["nbd_mean_response_time_ms", "nbd_std_response_time_ms"],
        "input_datasets": {},
        "output_datasets": {out_path.name: {"path": str(out_path), "sha256": _sha256(out_path)}},
    }
    manifest_path = out_path.parent / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[DatasetGenerator] Wrote run manifest to {manifest_path}")


def main_cli():
    parser = argparse.ArgumentParser(description="GridSentinel Labeled Dataset Generator")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument("--ticks", type=int, default=1500, help="Number of ticks to simulate")
    parser.add_argument("--out", type=str, default="data/generated/train_dataset_seed42.csv", help="Output CSV path")
    parser.add_argument("--mode", choices=["scenario_mix", "clean"], default="scenario_mix")
    parser.add_argument("--port-base", type=int, default=5021, help="First RTU TCP port for this process")
    parser.add_argument("--run-id", type=str, default="default", help="Stable identifier recorded in run_manifest.json")
    parser.add_argument("--normal-prob", type=float, default=0.25)
    parser.add_argument("--natural-fault-prob", type=float, default=0.25)
    parser.add_argument("--sensor-malfunction-prob", type=float, default=0.25)
    parser.add_argument("--cyber-prob", type=float, default=0.25)

    args = parser.parse_args()
    probabilities = {
        "normal": args.normal_prob,
        "natural_fault": args.natural_fault_prob,
        "sensor_malfunction": args.sensor_malfunction_prob,
        "cyber": args.cyber_prob,
    }
    asyncio.run(generate_dataset(
        seed=args.seed,
        total_ticks=args.ticks,
        out_csv=args.out,
        mode=args.mode,
        port_base=args.port_base,
        run_id=args.run_id,
        scenario_probabilities=probabilities,
    ))


if __name__ == "__main__":
    main_cli()
