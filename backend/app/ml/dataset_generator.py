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
import os
from pathlib import Path
import random
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from app.core.feeder import build_feeder
from app.ml.feature_engineering import FEATURE_SCHEMA, extract_features
from app.ot.rtu_server import rtu_pool
from app.ot.scenario_injector import scenario_injector
from app.ot.simulation_loop import sim_loop
from app.ot.traffic_logger import traffic_logger


async def generate_dataset(
    seed: int = 42,
    total_ticks: int = 2000,
    out_csv: Optional[str] = None,
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
    print(f"[DatasetGenerator] Starting generation: Seed={seed}, Ticks={total_ticks}...")
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

    try:
        for tick_idx in range(1, total_ticks + 1):
            # Check if we need to transition to a new scenario
            if scenario_remaining_ticks <= 0:
                scenario_injector.clear_all_scenarios(net=net)

                # Pick next scenario type roughly balanced
                # 35% Normal, 30% Natural Fault, 35% Cyber Intrusion
                p = random.random()
                if p < 0.35:
                    current_scenario_type = "Normal"
                    current_subtype = "normal"
                    scenario_remaining_ticks = random.randint(8, 20)
                elif p < 0.65:
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
                else:
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

            for rtu_id in range(1, 6):
                feats = extract_features(
                    traffic_events=recent_traffic,
                    state_estimation_result=se_res,
                    target_rtu_id=rtu_id,
                    polled_telemetry=polled_t,
                )

                # Determine RTU-specific label
                # If a cyber attack is active on a specific RTU, that RTU is Cyber Intrusion.
                # Other unaffected RTUs during targeted silent attacks remain Normal.
                if current_scenario_type == "Cyber Intrusion":
                    if rtu_id == attack_target_rtu:
                        rtu_top_label = "Cyber Intrusion"
                        rtu_sub_label = current_subtype
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

    return df


def main_cli():
    parser = argparse.ArgumentParser(description="GridSentinel Labeled Dataset Generator")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument("--ticks", type=int, default=1500, help="Number of ticks to simulate")
    parser.add_argument("--out", type=str, default="data/generated/train_dataset_seed42.csv", help="Output CSV path")

    args = parser.parse_args()
    asyncio.run(generate_dataset(seed=args.seed, total_ticks=args.ticks, out_csv=args.out))


if __name__ == "__main__":
    main_cli()
