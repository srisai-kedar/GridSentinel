"""Reconcile false-alarm episode tails for the isolated T2 latch experiment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from t2_followup_drift_hysteresis import base_alerts, grouped_episodes, latch, poisson_interval


def false_alarm_episodes(frame: pd.DataFrame, alerts: np.ndarray, include_sensor: bool) -> list[tuple[int, int]]:
    mask = frame.top_level_label.ne("Cyber Intrusion")
    if not include_sensor:
        mask &= frame.top_level_label.ne("Sensor Malfunction")
    sub = frame.loc[mask].copy()
    sub["alert"] = alerts[mask.to_numpy()]
    ticks = sorted(sub.loc[sub.alert, "tick"].astype(int).unique().tolist())
    if not ticks:
        return []
    episodes: list[tuple[int, int]] = []
    start = previous = ticks[0]
    for tick in ticks[1:]:
        if tick != previous + 1:
            episodes.append((start, previous))
            start = tick
        previous = tick
    episodes.append((start, previous))
    return episodes


def classify_tails(frame: pd.DataFrame, alerts: np.ndarray, grace_seconds: int = 4) -> dict:
    attacks = grouped_episodes(frame, "Cyber Intrusion")
    primary = false_alarm_episodes(frame, alerts, include_sensor=False)
    hold_tails = [episode for episode in primary if any(end < episode[0] <= end + grace_seconds for _, end in attacks)]
    genuine = [episode for episode in primary if episode not in hold_tails]
    exposure_seconds = int(frame.loc[frame.top_level_label.ne("Cyber Intrusion") & frame.top_level_label.ne("Sensor Malfunction"), "tick"].nunique())
    return {
        "grace_seconds": grace_seconds,
        "attack_episodes": attacks,
        "primary_false_alarm_episodes": primary,
        "hold_tail_episodes": hold_tails,
        "genuine_false_alarm_episodes": genuine,
        "counts": {
            "primary_false_alarm_episodes": len(primary),
            "hold_tail_episodes": len(hold_tails),
            "genuine_false_alarm_episodes": len(genuine),
            "primary_non_attack_seconds": exposure_seconds,
        },
        "genuine_rate": poisson_interval(len(genuine), exposure_seconds / 3600),
    }


def main(args: argparse.Namespace) -> None:
    test = pd.read_csv(args.test)
    raw = base_alerts(args.candidate, test)
    selected = latch(test, raw, k=2, n=3, m=4)
    result = {
        "inputs": {"test": str(args.test), "candidate": str(args.candidate)},
        "definition": "A primary false-alarm episode is a contiguous run of alert-positive tick seconds after excluding Cyber Intrusion and Sensor Malfunction rows. A hold tail starts strictly after a Cyber episode end and no later than end+4 seconds.",
        "raw_1_of_1": classify_tails(test, raw),
        "selected_2_of_3_m4": classify_tails(test, selected),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args())
