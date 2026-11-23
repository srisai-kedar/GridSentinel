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
from app.ot.scenario_registry import (
    apply_authorized_control_write,
    apply_breaker_open,
    apply_command_injection,
    apply_communication_stall,
    apply_drift,
    apply_fdi,
    apply_load_step,
    apply_natural_line_trip,
    apply_replay,
    apply_short_circuit,
    apply_sustained_setpoint,
    load_scenario_weights,
)


P3_SEED_BANDS = {
    "train": list(range(100, 120)),
    "validation": list(range(200, 205)),
    "test": list(range(300, 330)),
    "ood_test": list(range(400, 410)),
    "clean": list(range(500, 505)),
}


async def generate_dataset(
    seed: int = 42,
    total_ticks: int = 2000,
    out_csv: Optional[str] = None,
    mode: str = "scenario_mix",
    port_base: int = 5021,
    run_id: str = "default",
    scenario_probabilities: Optional[Dict[str, float]] = None,
    regime: Optional[str] = None,
    compressed_stress: bool = False,
    sim_seconds_per_tick: float = 1.0,
    profile_family: str = "default",
    load_noise_scale: Optional[float] = None,
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
    effective_regime = regime or ("clean" if mode == "clean" else "stress")
    probabilities = resolve_prevalence_regime(effective_regime, scenario_probabilities)
    if sim_seconds_per_tick <= 0:
        raise ValueError("sim_seconds_per_tick must be positive")
    configure_port_base(port_base)
    started = datetime.datetime.now(datetime.timezone.utc)
    perf_started = time.perf_counter()
    print(f"[DatasetGenerator] Starting generation: Seed={seed}, Ticks={total_ticks}, Mode={mode}, Run={run_id}...")
    random.seed(seed)
    np.random.seed(seed)
    initial_hour = random.uniform(0.0, 24.0)
    sim_loop.sim_minutes_per_tick = 15.0 if compressed_stress else sim_seconds_per_tick / 60.0
    sim_loop.sim_time_total_minutes = initial_hour * 60.0
    sim_loop.configure_operating_conditions(
        seed=seed,
        profile_family=profile_family,
        noise_scale=(0.03 if load_noise_scale is None else load_noise_scale),
        day_scale=random.uniform(0.95, 1.05),
    )

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
    episode_counter = 0
    episode_id = f"{run_id}:episode:0"
    scenario_params: Dict[str, Any] = {}
    scenario_onset_tick = 1
    scenario_end_tick = 0
    affected_rtus: List[int] = []

    telemetry_history: collections.deque = collections.deque(maxlen=3)
    residual_history: collections.deque = collections.deque(maxlen=6)

    try:
        for tick_idx in range(1, total_ticks + 1):
            # Check if we need to transition to a new scenario
            if scenario_remaining_ticks <= 0:
                scenario_injector.clear_all_scenarios(net=net)
                sim_loop.clear_load_step()
                episode_counter += 1
                episode_id = f"{run_id}:episode:{episode_counter}"
                scenario_onset_tick = tick_idx
                scenario_params = {}
                affected_rtus = []

                # Pick from the registry; explicit probabilities remain supported for compatibility.
                registry_weights = load_scenario_weights(effective_regime)
                p = random.random()
                selected = "normal"
                cumulative = 0.0
                for name, weight in registry_weights.items():
                    cumulative += weight
                    if p < cumulative:
                        selected = name
                        break
                if selected == "normal":
                    current_scenario_type = "Normal"
                    current_subtype = "normal"
                    scenario_remaining_ticks = random.randint(8, 20)
                elif selected == "load_step":
                    current_scenario_type = "Normal"
                    current_subtype = "benign_load_step"
                    scenario_remaining_ticks = random.randint(3, 12)
                    magnitude = random.uniform(-0.12, 0.12)
                    scenario_params = {"magnitude": magnitude}
                    apply_load_step(magnitude, scenario_remaining_ticks)
                elif selected == "authorized_control_write":
                    current_scenario_type = "Normal"
                    current_subtype = "authorized_control_write"
                    scenario_remaining_ticks = random.randint(3, 8)
                    scenario_params = {"rtu_id": random.choice([1, 2, 3, 4, 5]), "register_address": 3, "value": 2}
                    apply_authorized_control_write(**scenario_params)
                elif selected == "communication_stall":
                    current_scenario_type = "Normal"
                    current_subtype = "communication_stall"
                    scenario_remaining_ticks = random.randint(3, 8)
                    stalled_rtu = random.choice([1, 2, 3, 4, 5])
                    scenario_params = {"rtu_id": stalled_rtu}
                    apply_communication_stall(stalled_rtu, scenario_remaining_ticks)
                elif selected in {"natural_line_trip", "short_circuit"}:
                    current_scenario_type = "Natural Fault"
                    current_subtype = "line_trip" if selected == "natural_line_trip" else "short_circuit"
                    scenario_remaining_ticks = random.randint(4, 10)

                    if current_subtype == "line_trip":
                        target_line = random.choice([0, 1, 2, 3])
                        scenario_params = {"line_index": target_line}
                        apply_natural_line_trip(net=net, line_index=target_line)
                    elif current_subtype == "short_circuit":
                        target_bus = random.choice([2, 3, 4, 5])
                        fault_load_mw = random.uniform(1.8, 3.2)
                        fault_load_mvar = random.uniform(1.0, 2.0)
                        scenario_params = {
                            "bus_index": target_bus,
                            "fault_load_mw": fault_load_mw,
                            "fault_load_mvar": fault_load_mvar,
                        }
                        apply_short_circuit(
                            net=net,
                            bus_index=target_bus,
                            fault_load_mw=fault_load_mw,
                            fault_load_mvar=fault_load_mvar,
                            duration_ticks=scenario_remaining_ticks,
                        )
                elif selected == "drift":
                    current_scenario_type = "Sensor Malfunction"
                    current_subtype = "sensor_drift"
                    attack_target_rtu = random.choice([1, 2, 3, 4, 5])
                    affected_rtus = [attack_target_rtu]
                    scenario_remaining_ticks = random.randint(5, 15)
                    drift_val = random.choice([-0.08, -0.06, 0.07, 0.09])
                    scenario_params = {"rtu_id": attack_target_rtu, "drift_percent": drift_val, "mode": "step", "target": "V"}
                    apply_drift(
                        rtu_id=attack_target_rtu,
                        mode="step",
                        target="V",
                        magnitude=drift_val,
                        duration_ticks=scenario_remaining_ticks,
                    )
                elif selected in {"fdi", "command_injection", "breaker_open", "sustained_setpoint", "replay"} and mode == "scenario_mix":
                    current_scenario_type = "Cyber Intrusion"
                    current_subtype = "data_injection" if selected == "fdi" else selected
                    attack_target_rtu = random.choice([1, 2, 3, 4, 5])
                    affected_rtus = [attack_target_rtu]
                    scenario_remaining_ticks = random.randint(4, 12)

                    if current_subtype == "data_injection":
                        # Fabricate voltage (either overvoltage 1.08-1.25 or undervoltage 0.75-0.90)
                        fake_v = random.choice([random.uniform(1.08, 1.25), random.uniform(0.75, 0.90)])
                        sigma_multiple = random.choice([1, 2, 3, 5, 10, 25])
                        scenario_params = {"rtu_id": attack_target_rtu, "target": "V", "sigma_multiple": sigma_multiple, "voltage_pu": fake_v}
                        apply_fdi(
                            rtu_id=attack_target_rtu,
                            target="V",
                            sigma_multiple=sigma_multiple,
                            baseline={"voltage_pu": fake_v - 0.01, "p_mw": 0.2, "q_mvar": 0.1},
                            duration_ticks=scenario_remaining_ticks,
                        )
                    elif current_subtype == "command_injection":
                        # Send unauthorized command write to target RTU
                        fake_raw_val = random.randint(11000, 15000)
                        scenario_params = {"rtu_id": attack_target_rtu, "register_address": 0, "value": fake_raw_val}
                        await apply_command_injection(
                            rtu_id=attack_target_rtu,
                            register_address=0,
                            value=fake_raw_val,
                        )
                    elif current_subtype == "breaker_open":
                        line_index = random.choice([0, 1, 2, 3])
                        scenario_params = {"rtu_id": attack_target_rtu, "line_index": line_index, "variant": "breaker_open"}
                        await apply_breaker_open(net=net, rtu_id=attack_target_rtu, line_index=line_index)
                    elif current_subtype == "sustained_setpoint":
                        register_address = random.choice([0, 1, 2])
                        fake_raw_val = random.randint(11000, 15000) if register_address == 0 else random.randint(100, 500)
                        scenario_params = {"rtu_id": attack_target_rtu, "register_address": register_address, "value": fake_raw_val, "variant": "sustained_setpoint"}
                        await apply_sustained_setpoint(
                            rtu_id=attack_target_rtu,
                            register_address=register_address,
                            value=fake_raw_val,
                            duration_ticks=scenario_remaining_ticks,
                        )
                    elif current_subtype == "replay":
                        apply_replay(
                            rtu_id=attack_target_rtu,
                            duration_ticks=scenario_remaining_ticks,
                        )

                scenario_end_tick = tick_idx + scenario_remaining_ticks - 1

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

                target_row = rtu_id in affected_rtus
                attack_active = current_scenario_type == "Cyber Intrusion" and target_row
                evidence_visible = False
                if target_row and current_scenario_type in {"Cyber Intrusion", "Sensor Malfunction"}:
                    if current_subtype in {"data_injection", "sensor_drift"}:
                        evidence_visible = True
                    elif current_subtype == "replay":
                        evidence_visible = tick_idx > scenario_onset_tick
                    elif current_subtype == "command_injection":
                        evidence_visible = any(
                            event.get("observer_verified")
                            and event.get("target_rtu") == f"RTU_{rtu_id}"
                            and event.get("is_unexpected_write")
                            for event in recent_traffic
                        )

                record = dict(feats)
                record["tick"] = tick_idx
                record["rtu_id"] = rtu_id
                record["top_level_label"] = rtu_top_label
                record["subtype_label"] = rtu_sub_label
                record["episode_id"] = episode_id
                record["scenario_type"] = current_scenario_type
                record["scenario_params"] = json.dumps(scenario_params, sort_keys=True)
                record["onset_tick"] = scenario_onset_tick
                record["end_tick"] = scenario_end_tick
                record["attack_active"] = attack_active
                record["evidence_visible"] = evidence_visible
                record["affected_rtus"] = json.dumps(affected_rtus)
                records.append(add_run_provenance(
                    record,
                    run_id=run_id,
                    total_ticks=total_ticks,
                    sim_seconds_per_tick=sim_seconds_per_tick,
                    mode=mode,
                    regime=effective_regime,
                ))

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
            regime=effective_regime,
            compressed_stress=compressed_stress,
            sim_seconds_per_tick=sim_seconds_per_tick,
            profile_family=profile_family,
            initial_sim_time_hour=initial_hour,
        )

    return df


def resolve_prevalence_regime(
    regime: str, scenario_probabilities: Optional[Dict[str, float]] = None
) -> Dict[str, float]:
    """Resolve the documented P3 prevalence regimes."""
    defaults = {
        "stress": {"normal": 0.25, "natural_fault": 0.25, "sensor_malfunction": 0.25, "cyber": 0.25},
        "operational": {"normal": 0.97, "natural_fault": 0.01, "sensor_malfunction": 0.01, "cyber": 0.01},
        "clean": {"normal": 0.5, "natural_fault": 0.5},
    }
    if regime not in defaults:
        raise ValueError(f"Unsupported prevalence regime: {regime}")
    probabilities = scenario_probabilities or defaults[regime]
    return resolve_scenario_probabilities("clean" if regime == "clean" else "scenario_mix", probabilities)


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


def add_run_provenance(
    record: Dict[str, Any], *, run_id: str, total_ticks: int,
    sim_seconds_per_tick: float, mode: str, regime: str,
) -> Dict[str, Any]:
    """Attach provenance derived from the immutable generator invocation."""
    enriched = dict(record)
    enriched["run_id"] = run_id
    enriched["capture_id"] = run_id
    enriched["duration_hours"] = float(total_ticks * sim_seconds_per_tick / 3600.0)
    enriched["is_clean_run"] = bool(mode == "clean" or regime == "clean")
    return enriched


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
    elapsed_seconds: float, rows: int, regime: str, compressed_stress: bool,
    sim_seconds_per_tick: float, profile_family: str, initial_sim_time_hour: float,
) -> None:
    end = datetime.datetime.now(datetime.timezone.utc)
    manifest = {
        "task_id": "P3",
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
            "regime": regime,
            "compressed_stress": compressed_stress,
            "sim_seconds_per_tick": sim_seconds_per_tick,
            "profile_family": profile_family,
            "initial_sim_time_hour": initial_sim_time_hour,
        "regime": regime,
        },
        "seeds": {"python_random": seed, "numpy": seed},
        "started_at_utc": started.isoformat(),
        "ended_at_utc": end.isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 6),
        "throughput_ticks_per_second": round(total_ticks / elapsed_seconds, 6) if elapsed_seconds else None,
        "rows": rows,
        "timing_affected_columns": ["nbd_mean_response_time_ms", "nbd_std_response_time_ms"],
        "seed_bands": P3_SEED_BANDS,
        "input_datasets": {},
        "output_datasets": {
            out_path.name: {"path": str(out_path), "sha256": _sha256(out_path)},
        },
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
    parser.add_argument("--regime", choices=["stress", "operational", "clean"], default=None)
    parser.add_argument("--compressed-stress", action="store_true")
    parser.add_argument("--sim-seconds-per-tick", type=float, default=1.0)
    parser.add_argument("--profile-family", choices=["default", "ood"], default="default")
    parser.add_argument("--load-noise-scale", type=float, default=None)
    parser.add_argument("--port-base", type=int, default=5021, help="First RTU TCP port for this process")
    parser.add_argument("--run-id", type=str, default="default", help="Stable identifier recorded in run_manifest.json")
    parser.add_argument("--normal-prob", type=float, default=None)
    parser.add_argument("--natural-fault-prob", type=float, default=None)
    parser.add_argument("--sensor-malfunction-prob", type=float, default=None)
    parser.add_argument("--cyber-prob", type=float, default=None)

    args = parser.parse_args()
    probabilities = None
    if any(value is not None for value in (args.normal_prob, args.natural_fault_prob, args.sensor_malfunction_prob, args.cyber_prob)):
        probabilities = {
            "normal": args.normal_prob if args.normal_prob is not None else 0.0,
            "natural_fault": args.natural_fault_prob if args.natural_fault_prob is not None else 0.0,
            "sensor_malfunction": args.sensor_malfunction_prob if args.sensor_malfunction_prob is not None else 0.0,
            "cyber": args.cyber_prob if args.cyber_prob is not None else 0.0,
        }
    asyncio.run(generate_dataset(
        seed=args.seed,
        total_ticks=args.ticks,
        out_csv=args.out,
        mode=args.mode,
        port_base=args.port_base,
        run_id=args.run_id,
        scenario_probabilities=probabilities,
        regime=args.regime,
        compressed_stress=args.compressed_stress,
        sim_seconds_per_tick=args.sim_seconds_per_tick,
        profile_family=args.profile_family,
        load_noise_scale=args.load_noise_scale,
    ))


if __name__ == "__main__":
    main_cli()
