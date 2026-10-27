"""T2 end-to-end drift diagnosis and validation-only latch experiment."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import chi2

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.ml.classifier_service import ClassifierService, detect_sensor_drift_signature


def poisson_interval(count: int, exposure_hours: float) -> dict:
    alpha = 0.05
    low = 0.5 * chi2.ppf(alpha / 2, 2 * count) if count else 0.0
    high = 0.5 * chi2.ppf(1 - alpha / 2, 2 * (count + 1))
    return {"count": int(count), "exposure_hours": exposure_hours, "rate_per_hour": count / exposure_hours if exposure_hours else None, "poisson_95_low_per_hour": low / exposure_hours if exposure_hours else None, "poisson_95_high_per_hour": high / exposure_hours if exposure_hours else None}


def wilson(success: int, total: int) -> dict:
    if not total: return {"success": 0, "total": 0, "estimate": None, "low": 0.0, "high": 0.0}
    z = 1.959963984540054; p = success / total; den = 1 + z*z/total; c = (p + z*z/(2*total))/den; h = z*((p*(1-p)/total + z*z/(4*total*total))**0.5)/den
    return {"success": success, "total": total, "estimate": p, "low": c-h, "high": c+h}


def service_rows(bundle_path: Path, frame: pd.DataFrame) -> tuple[list[str], list[bool]]:
    svc = ClassifierService(model_path=str(bundle_path.resolve()))
    schema = svc.bundle.get("feature_schema", [])
    label_map = {0: "Cyber Intrusion", 1: "Natural Fault", 2: "Normal", 3: "Sensor Malfunction"}
    classes = [label_map.get(int(c), str(c)) if not isinstance(c, str) else c for c in svc.top_model.classes_]
    # Batch the exact model/threshold portion of ClassifierService._predict_untimed;
    # then apply the exact per-row drift interception rule. This avoids thousands
    # of sklearn feature-name warnings without changing inference semantics.
    proba = svc.top_model.predict_proba(frame[schema])
    cyber_idx = classes.index("Cyber Intrusion")
    verdicts = []
    drift_fires = []
    for row_values, (_, row) in zip(proba, frame.iterrows()):
        if row_values[cyber_idx] >= svc.decision_threshold:
            verdict = "Cyber Intrusion"
        else:
            masked = row_values.copy(); masked[cyber_idx] = 0.0
            verdict = classes[int(np.argmax(masked))]
        # Preserve the complete live feature dictionary for deterministic rules;
        # only the classifier vector is restricted to the loaded model schema.
        live_features = {k: float(row.get(k, 0.0)) for k in frame.columns if k not in {"tick", "rtu_id", "top_level_label", "subtype_label"}}
        drift = bool(detect_sensor_drift_signature(live_features))
        verdicts.append("Sensor Malfunction" if drift else str(verdict))
        drift_fires.append(drift)
    return verdicts, drift_fires


def grouped_episodes(frame: pd.DataFrame, label: str) -> list[tuple[int, int]]:
    ticks = sorted(frame.loc[frame.top_level_label.eq(label), "tick"].unique().astype(int).tolist())
    out = []
    if not ticks: return out
    start = prev = ticks[0]
    for t in ticks[1:]:
        if t != prev + 1: out.append((start, prev)); start = t
        prev = t
    out.append((start, prev)); return out


def verdict_counts(frame: pd.DataFrame, verdicts: list[str]) -> dict:
    values = pd.Series(verdicts).replace({"Sensor Malfunction": "SENSOR_DRIFT", "Cyber Intrusion": "CYBER", "Natural Fault": "NATURAL_FAULT", "Normal": "NORMAL"})
    return {k: int((values == k).sum()) for k in ("SENSOR_DRIFT", "CYBER", "NATURAL_FAULT", "NORMAL")}


def primary_confusion(frame: pd.DataFrame, verdicts: list[str]) -> dict:
    """Compute the three-class Cyber confusion counts excluding sensor rows."""
    actual_cyber = frame.top_level_label.eq("Cyber Intrusion").to_numpy()
    primary = ~frame.top_level_label.isin(["Cyber Intrusion", "Sensor Malfunction"]).to_numpy()
    predicted_cyber = np.asarray(verdicts) == "Cyber Intrusion"
    return {
        "tp": int((actual_cyber & predicted_cyber).sum()),
        "fp": int((primary & predicted_cyber).sum()),
        "fn": int((actual_cyber & ~predicted_cyber).sum()),
        "tn": int((primary & ~predicted_cyber).sum()),
    }


def episode_verdicts(frame: pd.DataFrame, verdicts: list[str], label: str) -> dict:
    keep = frame.top_level_label.eq(label).to_numpy()
    work = frame.loc[keep, ["tick", "top_level_label"]].copy(); work["verdict"] = np.asarray(verdicts)[keep]
    counts = {"SENSOR_DRIFT": 0, "CYBER": 0, "NATURAL_FAULT": 0, "NORMAL": 0}
    for start, end in grouped_episodes(frame, label):
        vals = work.loc[(work.tick >= start) & (work.tick <= end), "verdict"]
        norm = vals.replace({"Sensor Malfunction": "SENSOR_DRIFT", "Cyber Intrusion": "CYBER", "Natural Fault": "NATURAL_FAULT", "Normal": "NORMAL"})
        if len(norm): counts[str(norm.value_counts().index[0])] += 1
    return counts


def physics_summary(frame: pd.DataFrame) -> dict:
    fields = ["pcd_resid_concentration", "pcd_temporal_dv_dt_3tick", "pcd_voltage_dev_nominal", "pcd_max_lnr", "nbd_traffic_volume", "nbd_modbus_anomaly_rate"]
    out = {}
    for group, sub in (("sensor_drift", frame[frame.top_level_label.eq("Sensor Malfunction")]), ("fdi", frame[frame.subtype_label.eq("data_injection")])):
        out[group] = {f: {"n": int(sub[f].notna().sum()), "median": float(sub[f].median()), "p90": float(sub[f].quantile(.9)), "mean": float(sub[f].mean())} for f in fields}
    return out


def base_alerts(bundle_path: Path, frame: pd.DataFrame) -> np.ndarray:
    bundle = joblib.load(bundle_path); model = bundle["top_level_model"]; schema = bundle["feature_schema"]; classes = list(bundle.get("classes", model.classes_)); ci = classes.index("Cyber Intrusion"); threshold = float(bundle.get("decision_threshold", .5)); proba = model.predict_proba(frame[schema]); return proba[:, ci] >= threshold


def latch(frame: pd.DataFrame, raw: np.ndarray, k: int, n: int, m: int) -> np.ndarray:
    work = frame[["tick", "rtu_id"]].copy(); work["raw"] = raw; work["alert"] = False
    for _, group in work.groupby("rtu_id", sort=False):
        history, active, clear = [], False, 0
        for idx, row in group.sort_values("tick").iterrows():
            history.append(int(bool(row.raw))); history = history[-n:]
            if not active and sum(history) >= k: active = True; clear = 0
            if active:
                work.at[idx, "alert"] = True
                if bool(row.raw): clear = 0
                else: clear += 1
                if clear >= m: active = False
    return work.sort_index().alert.to_numpy()


def episode_metrics(frame: pd.DataFrame, alerts: np.ndarray) -> dict:
    true_eps = grouped_episodes(frame, "Cyber Intrusion"); ticks = set(frame.loc[alerts, "tick"].astype(int)); delays = []; detected = 0
    for start, end in true_eps:
        hits = [t for t in ticks if start <= t <= end]
        if hits: detected += 1; delays.append(min(hits)-start)
    def fa(include_sensor: bool) -> dict:
        mask = frame.top_level_label.ne("Cyber Intrusion")
        if not include_sensor: mask &= frame.top_level_label.ne("Sensor Malfunction")
        sub = frame[mask].copy(); sub["alert"] = alerts[mask.to_numpy()]; ts = sorted(sub.loc[sub.alert, "tick"].astype(int).unique().tolist()); episodes = sum(i == 0 or ts[i] != ts[i-1]+1 for i in range(len(ts))); seconds = int(sub.tick.nunique()); return poisson_interval(episodes, seconds/3600)
    primary = frame.top_level_label.ne("Cyber Intrusion") & frame.top_level_label.ne("Sensor Malfunction")
    y = frame.top_level_label.eq("Cyber Intrusion").to_numpy(); p = np.asarray(alerts)
    tp = int((y & p).sum()); fn = int((y & ~p).sum()); fp = int((primary.to_numpy() & p).sum()); tn = int((primary.to_numpy() & ~p).sum())
    return {"detected": detected, "total": len(true_eps), "episode_recall": detected/len(true_eps) if true_eps else None, "delays": delays, "median_delay": float(np.median(delays)) if delays else None, "p90_delay": float(np.percentile(delays, 90)) if delays else None, "per_reading": {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "recall": tp/(tp+fn) if tp+fn else None, "fpr": fp/(fp+tn) if fp+tn else None}, "fa_primary": fa(False), "fa_including_sensor": fa(True)}


def main(args: argparse.Namespace) -> None:
    train, val, test = [pd.read_csv(p) for p in (args.train, args.val, args.test)]
    prod_v, prod_rule = service_rows(args.production, test); cand_v, cand_rule = service_rows(args.candidate, test)
    categories = ["Sensor Malfunction", "Natural Fault", "Normal", "Cyber Intrusion"]
    drift = test.top_level_label.eq("Sensor Malfunction")
    rule_by_label = {}
    for name, mask in [("sensor_drift", drift), ("fdi", test.subtype_label.eq("data_injection")), ("replay", test.subtype_label.eq("replay")), ("command_injection", test.subtype_label.eq("command_injection")), ("natural_fault", test.top_level_label.eq("Natural Fault")), ("normal", test.top_level_label.eq("Normal"))]:
        m = mask.to_numpy(); rule_by_label[name] = {"fires": int(np.asarray(cand_rule)[m].sum()), "total": int(m.sum()), "interval": wilson(int(np.asarray(cand_rule)[m].sum()), int(m.sum()))}
    drift_ep = {"candidate": episode_verdicts(test, cand_v, "Sensor Malfunction"), "production": episode_verdicts(test, prod_v, "Sensor Malfunction"), "total": len(grouped_episodes(test, "Sensor Malfunction"))}
    # Validation-only ramp discriminator: existing drift signature plus abs(dv/dt) <= threshold.
    val_rule = service_rows(args.candidate, val)[1]
    thresholds = sorted(set([float(x) for x in val.pcd_temporal_dv_dt_3tick.abs().quantile(np.linspace(.05, .95, 19)).tolist()]))
    ramp_choices = []
    for threshold in thresholds:
        ramp = np.asarray(val_rule) & (val.pcd_temporal_dv_dt_3tick.abs().to_numpy() <= threshold)
        sensor = val.top_level_label.eq("Sensor Malfunction").to_numpy(); fdi = val.subtype_label.eq("data_injection").to_numpy(); cyber = val.top_level_label.eq("Cyber Intrusion").to_numpy()
        ramp_choices.append({"threshold": threshold, "sensor_recall": float(ramp[sensor].mean()), "fdi_wrong_drift": float(ramp[fdi].mean()), "fdi_detection_preserved": float((~ramp[fdi]).mean())})
    selected_ramp = sorted(ramp_choices, key=lambda x: (-x["sensor_recall"], x["fdi_wrong_drift"], x["threshold"]))[0] if ramp_choices else None
    cand_base = base_alerts(args.candidate, test)
    val_base = base_alerts(args.candidate, val)
    configs = [(1,1),(2,3),(2,4),(3,5)]; ms = [1,2,3,4,5]
    val_opts = []
    for k,n in configs:
        for m in ms:
            metrics = episode_metrics(val, latch(val, val_base, k,n,m)); val_opts.append({"k":k,"n":n,"m":m,"metrics":metrics})
    selected = sorted(val_opts, key=lambda x: (-x["metrics"]["episode_recall"], x["metrics"]["fa_including_sensor"]["rate_per_hour"], x["metrics"]["median_delay"] or 999, x["m"]))[0]
    selected_alerts = latch(test, cand_base, selected["k"], selected["n"], selected["m"])
    t2 = {"selected": selected, "test": episode_metrics(test, selected_alerts), "sensor_rows_called_cyber": int(selected_alerts[drift.to_numpy()].sum())}
    all_configs = {}
    for k,n in configs:
        best = sorted([x for x in val_opts if x["k"] == k and x["n"] == n], key=lambda x: (-x["metrics"]["episode_recall"], x["metrics"]["fa_including_sensor"]["rate_per_hour"], x["m"]))[0]
        all_configs[f"{k}-of-{n}"] = {"validation_selected_m": best["m"], "test": episode_metrics(test, latch(test, cand_base, k,n,best["m"]))}
    # Command visibility aging.
    cmd = test.subtype_label.eq("command_injection"); starts = []
    for start,end in grouped_episodes(test.assign(top_level_label=np.where(cmd, "Cyber Intrusion", test.top_level_label)), "Cyber Intrusion"):
        if cmd.loc[(test.tick >= start) & (test.tick <= end)].any(): starts.append(start)
    onset = []
    for _, row in test[cmd & test.nbd_unexpected_write_count.eq(0)].iterrows():
        prior = max([s for s in starts if s <= row.tick], default=row.tick); onset.append({"tick": int(row.tick), "ticks_since_onset": int(row.tick-prior), "aged_out_30_record_window": bool(row.tick-prior >= 30)})
    ramp_test = np.asarray(cand_rule) & (test.pcd_temporal_dv_dt_3tick.abs().to_numpy() <= selected_ramp["threshold"])
    ramp_fdi_wrong = int((ramp_test & test.subtype_label.eq("data_injection").to_numpy()).sum())
    result = {"service_path": {"candidate_sensor_rows": verdict_counts(test[drift].reset_index(drop=True), np.asarray(cand_v)[drift.to_numpy()]), "production_sensor_rows": verdict_counts(test[drift].reset_index(drop=True), np.asarray(prod_v)[drift.to_numpy()]), "candidate_primary_confusion": primary_confusion(test, cand_v), "production_primary_confusion": primary_confusion(test, prod_v), "candidate_sensor_episodes": drift_ep["candidate"], "production_sensor_episodes": drift_ep["production"], "sensor_episode_total": drift_ep["total"], "drift_rule_by_label": rule_by_label}, "physics_signature": physics_summary(test), "improvement_a_ramp": {"validation_choices": ramp_choices, "selected_validation_choice": selected_ramp, "test_base_rule_fires_on_sensor": int(np.asarray(cand_rule)[drift.to_numpy()].sum()), "test_ramp_rule_sensor": int(ramp_test[drift.to_numpy()].sum()), "test_sensor_rows_called_cyber_before": int((np.asarray(cand_v)[drift.to_numpy()] == "Cyber Intrusion").sum()), "test_sensor_rows_called_cyber_after": int(((np.asarray(cand_v)[drift.to_numpy()] == "Cyber Intrusion") & (~ramp_test[drift.to_numpy()])).sum()), "test_fdi_wrongly_labelled_drift": ramp_fdi_wrong, "decision": "isolated diagnostic only; no production rule changed"}, "improvement_b_latch_hold": {"selection_rule": "validation only: maximize episode recall, then minimize sensor-inclusive false-alarm rate, then minimize median delay", "validation_selected": {"k": selected["k"], "n": selected["n"], "m": selected["m"]}, "test_selected": t2["test"], "all_configs": all_configs}, "subtype_episodes": {}, "command_visibility_56_zero_write": {"rows": len(onset), "aged_out_count": int(sum(x["aged_out_30_record_window"] for x in onset)), "not_aged_out_count": int(sum(not x["aged_out_30_record_window"] for x in onset)), "rows": onset}, "subtyper_features": list(joblib.load(args.candidate)["feature_schema"]), "clean_run": {"status": "skipped", "reason": "dataset_generator has no clean-only mode; running it would mix scenarios and require modifying or approximating the generator"}}
    for subtype in ("data_injection", "replay", "command_injection"):
        mask = test.subtype_label.eq(subtype); sub = test[mask].copy(); sub["alert"] = cand_base[mask.to_numpy()]; result["subtype_episodes"][subtype] = episode_metrics(sub.rename(columns={"top_level_label":"top_level_label"}), sub.alert.to_numpy())
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8"); print(json.dumps(result, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--train", type=Path, required=True); ap.add_argument("--val", type=Path, required=True); ap.add_argument("--test", type=Path, required=True); ap.add_argument("--candidate", type=Path, required=True); ap.add_argument("--production", type=Path, required=True); ap.add_argument("--out", type=Path, required=True); main(ap.parse_args())
