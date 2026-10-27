"""T1 reconciliation plus validation-only persistence/cooldown analysis."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


def wilson(success: int, total: int) -> dict:
    if total == 0:
        return {"success": 0, "total": 0, "estimate": None, "wilson_95_low": 0.0, "wilson_95_high": 0.0}
    z = 1.959963984540054
    p = success / total
    den = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / den
    half = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5) / den
    return {"success": success, "total": total, "estimate": p, "wilson_95_low": centre - half, "wilson_95_high": centre + half}


def threshold_labels(bundle: dict, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    model = bundle["top_level_model"]
    schema = bundle["feature_schema"]
    classes = list(bundle.get("classes", model.classes_))
    cyber_idx = classes.index("Cyber Intrusion")
    proba = model.predict_proba(frame[schema])
    threshold = float(bundle.get("decision_threshold", 0.5))
    labels = []
    for row in proba:
        if row[cyber_idx] >= threshold:
            labels.append("Cyber Intrusion")
        else:
            non_cyber = row.copy(); non_cyber[cyber_idx] = -1.0
            labels.append(classes[int(np.argmax(non_cyber))])
    return np.asarray(labels), proba[:, cyber_idx]


def attack_episodes(frame: pd.DataFrame) -> list[tuple[int, int]]:
    ticks = sorted(frame.loc[frame.top_level_label.eq("Cyber Intrusion"), "tick"].unique().tolist())
    if not ticks:
        return []
    out = []
    start = previous = int(ticks[0])
    for tick in ticks[1:]:
        tick = int(tick)
        if tick != previous + 1:
            out.append((start, previous)); start = tick
        previous = tick
    out.append((start, previous))
    return out


def apply_persistence(frame: pd.DataFrame, raw_alert: np.ndarray, k: int, n: int, cooldown: int) -> np.ndarray:
    work = frame[["tick", "rtu_id"]].copy()
    work["raw_alert"] = raw_alert
    work["alert"] = False
    for rtu, group in work.groupby("rtu_id", sort=False):
        history: list[int] = []
        last_alert = -10**9
        for idx, row in group.sort_values("tick").iterrows():
            history.append(int(bool(row.raw_alert)))
            if len(history) > n:
                history.pop(0)
            qualifies = sum(history) >= k
            if qualifies and int(row.tick) > last_alert + cooldown:
                work.at[idx, "alert"] = True
                last_alert = int(row.tick)
    return work.sort_index().alert.to_numpy()


def episode_metrics(frame: pd.DataFrame, alerts: np.ndarray) -> dict:
    work = frame[["tick", "top_level_label"]].copy(); work["alert"] = alerts
    true_episodes = attack_episodes(frame)
    alert_ticks = set(work.loc[work.alert, "tick"].astype(int).tolist())
    delays = []
    detected = 0
    for start, end in true_episodes:
        hits = [t for t in alert_ticks if start <= t <= end]
        if hits:
            detected += 1; delays.append(min(hits) - start)
    def false_episodes(include_sensor: bool) -> dict:
        allowed = work.top_level_label.ne("Cyber Intrusion")
        if not include_sensor:
            allowed &= work.top_level_label.ne("Sensor Malfunction")
        subset = work[allowed]
        ticks = sorted(subset.loc[subset.alert, "tick"].astype(int).unique().tolist())
        count = 0
        for i, tick in enumerate(ticks):
            if i == 0 or tick != ticks[i - 1] + 1: count += 1
        seconds = int(subset.tick.nunique())
        return {"episodes": count, "non_attack_seconds": seconds, "episodes_per_hour": count / (seconds / 3600) if seconds else None}
    return {"attack_episodes": len(true_episodes), "detected": detected, "episode_recall": detected / len(true_episodes) if true_episodes else None, "delays_seconds": delays, "median_delay_seconds": float(np.median(delays)) if delays else None, "p90_delay_seconds": float(np.percentile(delays, 90)) if delays else None, "false_alarm_primary": false_episodes(False), "false_alarm_including_sensor": false_episodes(True)}


def config_metrics(frame: pd.DataFrame, raw_alert: np.ndarray, k: int, n: int, cooldown: int) -> dict:
    alerts = apply_persistence(frame, raw_alert, k, n, cooldown)
    non_attack = frame.top_level_label.ne("Cyber Intrusion") & frame.top_level_label.ne("Sensor Malfunction")
    y = frame.top_level_label.eq("Cyber Intrusion").to_numpy()
    tp = int((y & alerts).sum()); fn = int((y & ~alerts).sum()); fp = int((non_attack.to_numpy() & alerts).sum()); tn = int((non_attack.to_numpy() & ~alerts).sum())
    return {"k": k, "n": n, "cooldown_seconds": cooldown, "per_reading": {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "recall": wilson(tp, tp + fn), "fpr": wilson(fp, fp + tn)}, "episodes": episode_metrics(frame, alerts)}


def choose_cooldown(frame: pd.DataFrame, raw_alert: np.ndarray, k: int, n: int) -> dict:
    candidates = [config_metrics(frame, raw_alert, k, n, cooldown) for cooldown in (0, 1, 2, 3, 5)]
    return sorted(candidates, key=lambda x: (-x["episodes"]["episode_recall"], x["episodes"]["false_alarm_primary"]["episodes_per_hour"], x["episodes"]["median_delay_seconds"] or 10**9, x["cooldown_seconds"]))[0]


def main(args: argparse.Namespace) -> dict:
    train, val, test = [pd.read_csv(path) for path in (args.train, args.val, args.test)]
    candidate = joblib.load(args.candidate); old = joblib.load(args.production)
    cand_test_labels, _ = threshold_labels(candidate, test); old_test_labels, _ = threshold_labels(old, test)
    sensor = test.top_level_label.eq("Sensor Malfunction")
    def prediction_counts(labels: np.ndarray) -> dict:
        return {name: int(((labels[sensor.to_numpy()]) == name).sum()) for name in ("Cyber Intrusion", "Natural Fault", "Normal")}
    cyber = test.top_level_label.eq("Cyber Intrusion")
    write_positive = test.nbd_unexpected_write_count.gt(0)
    command = test.subtype_label.eq("command_injection")
    non_attack = ~cyber
    subtype = {}
    cand_sub = candidate["subtype_model"].predict(test[candidate["feature_schema"]])
    old_sub = old["subtype_model"].predict(test[old["feature_schema"]])
    for name in ("command_injection", "data_injection", "replay"):
        mask = test.subtype_label.eq(name).to_numpy()
        cand_detect = cand_test_labels[mask].__eq__("Cyber Intrusion")
        old_detect = old_test_labels[mask].__eq__("Cyber Intrusion")
        cand_detect_idx = mask & (cand_test_labels == "Cyber Intrusion")
        old_detect_idx = mask & (old_test_labels == "Cyber Intrusion")
        subtype[name] = {"candidate_detection": wilson(int(cand_detect.sum()), int(mask.sum())), "old_production_detection": wilson(int(old_detect.sum()), int(mask.sum())), "candidate_subtype_accuracy_all_attack_readings": wilson(int((cand_sub[mask] == name).sum()), int(mask.sum())), "old_subtype_accuracy_all_attack_readings": wilson(int((old_sub[mask] == name).sum()), int(mask.sum())), "candidate_subtype_accuracy_among_detected": wilson(int((cand_sub[cand_detect_idx] == name).sum()), int(cand_detect.sum())), "old_subtype_accuracy_among_detected": wilson(int((old_sub[old_detect_idx] == name).sum()), int(old_detect.sum()))}
    configs = [(1, 1), (2, 3), (2, 4), (3, 5)]
    val_labels, _ = threshold_labels(candidate, val)
    chosen = {f"{k}-of-{n}": choose_cooldown(val, val_labels == "Cyber Intrusion", k, n) for k, n in configs}
    test_metrics = {name: config_metrics(test, cand_test_labels == "Cyber Intrusion", v["k"], v["n"], v["cooldown_seconds"]) for name, v in chosen.items()}
    selected_name = sorted(chosen, key=lambda name: (-chosen[name]["episodes"]["episode_recall"], chosen[name]["episodes"]["false_alarm_primary"]["episodes_per_hour"], chosen[name]["episodes"]["median_delay_seconds"] or 10**9, chosen[name]["cooldown_seconds"]))[0]
    result = {"part_a": {"test_rows": len(test), "primary_rows": int((~sensor).sum()), "excluded_sensor_rows": int(sensor.sum()), "candidate_sensor_predictions": prediction_counts(cand_test_labels), "old_production_sensor_predictions": prediction_counts(old_test_labels), "candidate_subtypes": subtype, "write_visibility": {"command_injection_rows": int(command.sum()), "command_write_gt0": int((command & write_positive).sum()), "command_write_gt0_fraction": wilson(int((command & write_positive).sum()), int(command.sum())), "non_attack_rows": int(non_attack.sum()), "non_attack_write_gt0": int((non_attack & write_positive).sum()), "candidate_flagged_command_write_gt0": int((command & write_positive & (cand_test_labels == "Cyber Intrusion")).sum()), "candidate_missed_command_write_gt0": int((command & write_positive & (cand_test_labels != "Cyber Intrusion")).sum())}}, "part_b": {"selection_rule": "For each k/n, cooldown selected on validation only: maximize episode recall, then minimize primary false-alarm episodes/hour, then minimize median delay.", "validation_by_config": chosen, "test_by_config": test_metrics, "validation_selected_config": selected_name}}
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--train", type=Path, required=True); ap.add_argument("--val", type=Path, required=True); ap.add_argument("--test", type=Path, required=True); ap.add_argument("--candidate", type=Path, required=True); ap.add_argument("--production", type=Path, required=True); ap.add_argument("--out", type=Path, required=True); main(ap.parse_args())
