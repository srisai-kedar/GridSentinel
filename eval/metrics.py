"""Cluster-aware evaluation metrics for P5.

This module accepts already-materialized observations and never reads datasets.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable, Mapping

from scipy.stats import chi2


def _rows(observations: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in observations]


def _group_ticks(rows: list[dict[str, Any]]) -> dict[tuple[str, int], list[dict[str, Any]]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["run_id"]), int(row["tick"]))].append(row)
    return grouped


def _episodes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        episode_id = row.get("episode_id")
        if episode_id is not None and row.get("attack_active"):
            grouped[(str(row["run_id"]), str(episode_id))].append(row)
    output = []
    for (run_id, episode_id), members in grouped.items():
        ticks = [int(row["tick"]) for row in members]
        output.append({
            "run_id": run_id,
            "episode_id": episode_id,
            "scenario_type": str(members[0].get("scenario_type", "unknown")),
            "onset_tick": min(ticks),
            "end_tick": max(ticks),
        })
    return output


def _system_alerts(rows: list[dict[str, Any]]) -> dict[str, set[int]]:
    alerts: dict[str, set[int]] = defaultdict(set)
    for (run_id, tick), members in _group_ticks(rows).items():
        if any(bool(row.get("alert", row.get("predicted_alert", False))) for row in members):
            alerts[run_id].add(tick)
    return alerts


def _merge_alert_events(ticks: set[int], gap: int) -> list[tuple[int, int]]:
    if not ticks:
        return []
    ordered = sorted(ticks)
    events: list[tuple[int, int]] = []
    start = previous = ordered[0]
    for tick in ordered[1:]:
        if tick - previous <= gap + 1:
            previous = tick
            continue
        events.append((start, previous))
        start = previous = tick
    events.append((start, previous))
    return events


def poisson_interval(events: int, hours: float, alpha: float = 0.05) -> tuple[float, float]:
    """Exact Poisson rate interval for events/hour using chi-square limits."""
    if hours <= 0:
        raise ValueError("hours must be positive")
    if events < 0:
        raise ValueError("events must be non-negative")
    lower_count = 0.0 if events == 0 else 0.5 * float(chi2.ppf(alpha / 2.0, 2 * events))
    upper_count = 0.5 * float(chi2.ppf(1.0 - alpha / 2.0, 2 * (events + 1)))
    return lower_count / hours, upper_count / hours


def evaluate(
    observations: Iterable[Mapping[str, Any]],
    *,
    clean_runs: Mapping[str, float] | None = None,
    gap: int = 0,
    tail: int = 0,
    grace: int = 0,
) -> dict[str, Any]:
    """Compute reading, evidence, tick, episode, delay, and false-alarm metrics."""
    rows = _rows(observations)
    if gap < 0 or tail < 0 or grace < 0:
        raise ValueError("gap, tail, and grace must be non-negative")
    alerts = _system_alerts(rows)
    episode_records = _episodes(rows)
    episode_results = []
    for episode in episode_records:
        candidate_ticks = sorted(
            tick for tick in alerts.get(episode["run_id"], set())
            if episode["onset_tick"] <= tick <= episode["end_tick"] + grace
        )
        detected = bool(candidate_ticks)
        episode_results.append({
            **episode,
            "detected": detected,
            "delay_ticks": candidate_ticks[0] - episode["onset_tick"] if detected else None,
        })

    alert_events = []
    false_events = []
    true_events = []
    for run_id, ticks in alerts.items():
        for start, end in _merge_alert_events(ticks, gap):
            overlaps = [
                episode for episode in episode_records
                if episode["run_id"] == run_id
                and start <= episode["end_tick"] + tail
                and end >= episode["onset_tick"]
            ]
            event = {"run_id": run_id, "start_tick": start, "end_tick": end, "true": bool(overlaps)}
            alert_events.append(event)
            (true_events if event["true"] else false_events).append(event)

    reading_alerts = [bool(row.get("alert", row.get("predicted_alert", False))) for row in rows]
    attack_rows = [row for row in rows if bool(row.get("attack_active"))]
    visible_rows = [row for row in rows if bool(row.get("evidence_visible"))]
    non_attack_rows = [row for row in rows if not bool(row.get("attack_active"))]
    tick_groups = _group_ticks(rows)
    attack_ticks = {
        (run_id, tick) for (run_id, tick), members in tick_groups.items()
        if any(bool(row.get("attack_active")) for row in members)
    }
    alarmed_attack_ticks = {
        key for key, members in tick_groups.items()
        if key in attack_ticks and any(bool(row.get("alert", row.get("predicted_alert", False))) for row in members)
    }
    clean_hours = float(sum(clean_runs.values())) if clean_runs else 0.0
    clean_false_events = [event for event in false_events if not clean_runs or event["run_id"] in clean_runs]
    fa_rate = (len(clean_false_events) / clean_hours) if clean_hours else None
    fa_interval = poisson_interval(len(clean_false_events), clean_hours) if clean_hours else None
    per_type: dict[str, dict[str, Any]] = {}
    for episode in episode_results:
        entry = per_type.setdefault(episode["scenario_type"], {"episodes": 0, "detected": 0, "delays": []})
        entry["episodes"] += 1
        entry["detected"] += int(episode["detected"])
        if episode["delay_ticks"] is not None:
            entry["delays"].append(episode["delay_ticks"])
    for entry in per_type.values():
        entry["recall"] = entry["detected"] / entry["episodes"] if entry["episodes"] else None
        entry["median_delay_ticks"] = sorted(entry["delays"])[len(entry["delays"]) // 2] if entry["delays"] else None
        entry["delays"] = sorted(entry["delays"])
    return {
        "configuration": {"gap": gap, "tail": tail, "grace": grace},
        "reading": {"rows": len(rows), "alerts": sum(reading_alerts), "attack_rows": len(attack_rows), "non_attack_rows": len(non_attack_rows)},
        "evidence_visible": {"rows": len(visible_rows), "alerts": sum(bool(row.get("alert", row.get("predicted_alert", False))) for row in visible_rows)},
        "tick": {"ticks": len(tick_groups), "attack_ticks": len(attack_ticks), "alarmed_attack_ticks": len(alarmed_attack_ticks), "recall": len(alarmed_attack_ticks) / len(attack_ticks) if attack_ticks else None},
        "episode": {"episodes": len(episode_results), "detected": sum(int(item["detected"]) for item in episode_results), "recall": sum(int(item["detected"]) for item in episode_results) / len(episode_results) if episode_results else None, "delays": [item["delay_ticks"] for item in episode_results if item["delay_ticks"] is not None]},
        "per_type": per_type,
        "alert_events": {"total": len(alert_events), "true": len(true_events), "false": len(false_events)},
        "false_alarms": {"clean_hours": clean_hours, "events": len(clean_false_events), "per_hour": fa_rate, "exact_poisson_95": fa_interval},
        "episode_results": episode_results,
    }
