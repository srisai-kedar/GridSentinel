"use client";

import React, { useMemo } from "react";
import { ArrowUpRight, CheckCircle2, ShieldAlert, TriangleAlert } from "lucide-react";
import { LiveSocketPayload, RTUVerdict, VerdictType } from "@/lib/types";
import {
  getNetworkEvidenceSummary,
  getPhysicsEvidenceSummary,
  getRecommendedAction,
  getRtuAssetLabel,
  getVerdictColor,
} from "@/lib/alertText";

interface EvidencePanelProps {
  latestState: LiveSocketPayload | null;
  selectedBusId?: number | null;
}

const busToRtu: Record<number, number> = { 1: 1, 2: 2, 3: 3, 4: 4, 5: 5 };

function verdictIcon(verdict: VerdictType) {
  if (verdict === "Cyber Intrusion") return <ShieldAlert size={14} />;
  if (verdict === "Natural Fault") return <TriangleAlert size={14} />;
  return <CheckCircle2 size={14} />;
}

export const EvidencePanel: React.FC<EvidencePanelProps> = ({ latestState, selectedBusId }) => {
  const selected = useMemo(() => {
    const verdicts = Object.values(latestState?.ml_verdicts || {});
    const selectedRtu = selectedBusId ? busToRtu[selectedBusId] : undefined;
    return (
      (selectedRtu && verdicts.find((item) => item.rtu_id === selectedRtu)) ||
      verdicts.find((item) => item.verdict !== "Normal") ||
      verdicts[0] ||
      null
    ) as RTUVerdict | null;
  }, [latestState, selectedBusId]);

  const verdict = selected?.verdict || "No Data";
  const color = getVerdictColor(verdict);
  const networkEvidence = selected?.network_evidence || getNetworkEvidenceSummary(verdict, selected?.subtype || "normal");
  const physicsEvidence = selected?.physics_evidence || getPhysicsEvidenceSummary(verdict, selected?.subtype || "normal");

  return (
    <section className="scada-surface scada-evidence-panel" aria-labelledby="evidence-heading">
      <div className="scada-section-header compact-header">
        <div>
          <span className="scada-kicker">Engineering investigation</span>
          <h2 id="evidence-heading">Explainable evidence</h2>
        </div>
        {selected && <span className="scada-evidence-asset">{getRtuAssetLabel(selected.rtu_id)}</span>}
      </div>

      {!latestState || !selected ? (
        <div className="scada-empty-state">Evidence will populate when telemetry and an RTU verdict are available.</div>
      ) : (
        <div className="scada-evidence-body">
          <div className="scada-verdict-row" style={{ color }}>
            <span className="scada-verdict-icon">{verdictIcon(verdict)}</span>
            <div><span>Fusion verdict</span><strong>{verdict}</strong></div>
            <div className="scada-confidence"><span>Confidence</span><strong>{(selected.confidence * 100).toFixed(0)}%</strong></div>
          </div>
          <div className="scada-evidence-line"><span>Network evidence</span><p>{networkEvidence.replace(/^Network:\s*/, "")}</p></div>
          <div className="scada-evidence-line"><span>Physics evidence</span><p>{physicsEvidence.replace(/^Physics:\s*/, "")}</p></div>
          <div className="scada-next-action"><span>Next operator check</span><strong>{getRecommendedAction(verdict, selected.subtype || "normal")}</strong><ArrowUpRight size={14} /></div>
        </div>
      )}
    </section>
  );
};
