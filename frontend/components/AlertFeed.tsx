"use client";

import React, { useEffect, useRef, useState } from "react";
import { AlertCircle, Bell, CheckCircle2, ShieldAlert, Trash2, TriangleAlert } from "lucide-react";
import { LiveSocketPayload, RTUVerdict, VerdictType } from "@/lib/types";
import { formatAlert, getRtuAssetLabel, getVerdictColor } from "@/lib/alertText";

export interface AlertFeedItem {
  id: string;
  rtuId: number;
  simTime: string;
  wallTimestamp: string;
  verdict: VerdictType;
  subtype: string | null;
  confidence: number;
  message: string;
  previousVerdict?: VerdictType;
  networkEvidence?: string;
  physicsEvidence?: string;
  conclusion?: string;
}

interface AlertFeedProps {
  latestState: LiveSocketPayload | null;
  onAlertClick?: (rtuId: number) => void;
  onNewVerdictChange?: (item: AlertFeedItem) => void;
}

type AlertFilter = "ALL" | "CYBER" | "FAULT" | "NORMAL";

export const AlertFeed: React.FC<AlertFeedProps> = ({ latestState, onAlertClick, onNewVerdictChange }) => {
  const [alerts, setAlerts] = useState<AlertFeedItem[]>([]);
  const [filter, setFilter] = useState<AlertFilter>("ALL");
  const previousRef = useRef<Record<number, { verdict: VerdictType; subtype: string | null }>>({});

  useEffect(() => {
    if (!latestState?.ml_verdicts) return;
    const newItems: AlertFeedItem[] = [];
    Object.entries(latestState.ml_verdicts).forEach(([id, data]) => {
      const rtuId = Number(id);
      const verdict = data.verdict as VerdictType;
      const previous = previousRef.current[rtuId];
      const changed = previous && (previous.verdict !== verdict || previous.subtype !== data.subtype);
      if (changed || (!previous && verdict !== "Normal")) {
        const item: AlertFeedItem = {
          id: `alert-${Date.now()}-${rtuId}-${Math.random().toString(36).slice(2, 6)}`,
          rtuId,
          simTime: latestState.sim_time || "--:--:--",
          wallTimestamp: new Date().toISOString(),
          verdict,
          subtype: data.subtype,
          confidence: data.confidence,
          message: formatAlert(verdict, data.subtype, rtuId, data.confidence),
          previousVerdict: previous?.verdict,
          networkEvidence: data.network_evidence,
          physicsEvidence: data.physics_evidence,
          conclusion: data.conclusion,
        };
        newItems.push(item);
        onNewVerdictChange?.(item);
      }
      previousRef.current[rtuId] = { verdict, subtype: data.subtype };
    });
    if (newItems.length) setAlerts((current) => [...newItems, ...current].slice(0, 100));
  }, [latestState, onNewVerdictChange]);

  const counts = {
    cyber: alerts.filter((item) => item.verdict === "Cyber Intrusion").length,
    fault: alerts.filter((item) => item.verdict === "Natural Fault").length,
    normal: alerts.filter((item) => item.verdict === "Normal").length,
  };
  const visibleAlerts = alerts.filter((item) =>
    filter === "CYBER" ? item.verdict === "Cyber Intrusion" :
    filter === "FAULT" ? item.verdict === "Natural Fault" :
    filter === "NORMAL" ? item.verdict === "Normal" : true
  );

  const iconFor = (verdict: VerdictType) => {
    if (verdict === "Cyber Intrusion") return <ShieldAlert size={15} />;
    if (verdict === "Natural Fault") return <TriangleAlert size={15} />;
    if (verdict === "Normal") return <CheckCircle2 size={15} />;
    return <AlertCircle size={15} />;
  };

  return (
    <section className="scada-surface scada-alert-feed" aria-labelledby="alert-feed-heading">
      <div className="scada-section-header compact-header">
        <div><span className="scada-kicker">What is happening now</span><h2 id="alert-feed-heading">Incident queue</h2></div>
        <div className="scada-feed-actions"><span>{visibleAlerts.length} shown</span>{alerts.length > 0 && <button onClick={() => setAlerts([])} title="Clear incident queue"><Trash2 size={14} /></button>}</div>
      </div>
      <div className="scada-alert-filters">
        {(["ALL", "CYBER", "FAULT", "NORMAL"] as AlertFilter[]).map((item) => (
          <button key={item} className={`${filter === item ? "is-active" : ""} ${item.toLowerCase()}`} onClick={() => setFilter(item)}>
            {item === "ALL" ? "All" : item === "CYBER" ? `Cyber · ${counts.cyber}` : item === "FAULT" ? `Fault · ${counts.fault}` : `Normal · ${counts.normal}`}
          </button>
        ))}
      </div>
      <div className="scada-alert-list">
        {visibleAlerts.length === 0 ? (
          <div className="scada-empty-state"><Bell size={18} /><strong>No state transitions</strong><span>Physical faults and cyber anomalies will appear here as the classifier changes state.</span></div>
        ) : visibleAlerts.map((alert) => {
          const color = getVerdictColor(alert.verdict);
          return (
            <button key={alert.id} className="scada-alert-row" onClick={() => onAlertClick?.(alert.rtuId)} style={{ borderLeftColor: color }}>
              <span className="scada-alert-icon" style={{ color }}>{iconFor(alert.verdict)}</span>
              <span className="scada-alert-copy">
                <span className="scada-alert-row-head"><strong>{getRtuAssetLabel(alert.rtuId)}</strong><time>{alert.simTime}</time></span>
                <span className="scada-alert-message">{alert.message}</span>
                <span className="scada-alert-row-foot"><em style={{ color }}>{alert.verdict}{alert.subtype ? ` · ${alert.subtype.replaceAll("_", " ")}` : ""}</em><span>confidence {(alert.confidence * 100).toFixed(0)}%</span></span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
};
