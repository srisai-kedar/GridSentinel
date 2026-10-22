"use client";

import React, { useEffect, useState } from "react";
import { getClassifierBenchmark } from "@/lib/api";
import type { MLBenchmarkResponse } from "@/lib/types";

function formatPercent(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : "—";
}
function formatMs(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(2)} ms` : "—";
}
function formatCount(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString() : "—";
}

export function MLBenchmarkPanel() {
  const [benchmark, setBenchmark] = useState<MLBenchmarkResponse | null>(null);
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const next = await getClassifierBenchmark();
        if (!cancelled) setBenchmark(next);
      } catch {
        if (!cancelled) setBenchmark({
          available: false, status: "error", feature_schema_version: "unknown",
          message: "The backend benchmark endpoint is not currently reachable.",
        });
      }
    };
    void load();
    const interval = window.setInterval(() => void load(), 60_000);
    return () => { cancelled = true; window.clearInterval(interval); };
  }, []);

  const available = benchmark?.available === true;
  const benchmarkDate = benchmark?.evaluated_at && Number.isFinite(Date.parse(benchmark.evaluated_at))
    ? new Date(benchmark.evaluated_at).toLocaleString() : null;
  const cells = [
    { label: "Overall accuracy", value: formatPercent(benchmark?.overall_accuracy) },
    { label: "Cyber recall", value: formatPercent(benchmark?.cyber_recall) },
    { label: "Cyber precision", value: formatPercent(benchmark?.cyber_precision) },
    { label: "Cyber false-negative rate", value: formatPercent(benchmark?.cyber_fnr) },
    { label: "Cyber false-positive rate", value: formatPercent(benchmark?.cyber_fpr) },
    { label: "Cyber F1", value: formatPercent(benchmark?.cyber_f1) },
    { label: "Inference latency", value: formatMs(benchmark?.latency_ms_per_verdict) },
  ];
  return (
    <section className="scada-surface scada-ml-benchmark" aria-label="ML model validation benchmark">
      <div className="scada-ml-benchmark-header">
        <div><span className="scada-kicker">MODEL VALIDATION</span><h2>Deployed ML benchmark</h2></div>
        <span className={`scada-ml-benchmark-status ${available ? "is-current" : "is-stale"}`}>
          {available ? "SCHEMA MATCH" : benchmark?.status === "stale" ? "STALE REPORT" : "NOT VERIFIED"}
        </span>
      </div>
      {available ? <>
        <div className="scada-ml-benchmark-meta">
          <strong>{benchmark?.model_name || "Unknown model"}</strong>
          <span>Feature schema {benchmark?.feature_schema_version}</span>
          <span>Threshold {typeof benchmark?.decision_threshold === "number" ? benchmark.decision_threshold.toFixed(2) : "—"}</span>
        </div>
        <div className="scada-ml-benchmark-grid">
          {cells.map(cell => <div className="scada-ml-benchmark-cell" key={cell.label}><span>{cell.label}</span><strong>{cell.value}</strong></div>)}
        </div>
        <p className="scada-ml-benchmark-note">
          Held-out simulated test set · {formatCount(benchmark?.n_test_samples)} samples · {formatCount(benchmark?.feature_count)} features
          {benchmarkDate ? ` · evaluated ${benchmarkDate}` : ""}. {benchmark?.source_note || "Simulation-only results; not field-validated."}
        </p>
      </> : <p className="scada-ml-benchmark-note">
        {benchmark?.message || "A verified benchmark for the active feature schema is not available yet."}
        {benchmark?.report_schema_version ? ` Stored report schema: ${benchmark.report_schema_version}; active schema: ${benchmark.feature_schema_version}.` : ""}
        {" "}Historical figures are not displayed as current results.
      </p>}
    </section>
  );
}
