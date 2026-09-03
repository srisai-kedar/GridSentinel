"use client";

import React from "react";
import { Activity, CheckCircle2, Clock3, Radio, ShieldAlert, TriangleAlert, Wifi, WifiOff, Zap } from "lucide-react";
import { ConnectionStatus, LiveSocketPayload, StreamStatus, VerdictType } from "@/lib/types";
import { SCADA_COLORS } from "@/lib/alertText";

interface StatusBarProps {
  connectionStatus: ConnectionStatus;
  latestState: LiveSocketPayload | null;
  streamStatus?: StreamStatus;
}

export const StatusBar: React.FC<StatusBarProps> = ({ connectionStatus, latestState, streamStatus = "connecting" }) => {
  let verdict: VerdictType = "Normal";
  const verdicts = Object.values(latestState?.ml_verdicts || {});
  if (!latestState) verdict = "No Data";
  else if (verdicts.some((item) => item.verdict === "Cyber Intrusion")) verdict = "Cyber Intrusion";
  else if (verdicts.some((item) => item.verdict === "Natural Fault")) verdict = "Natural Fault";

  const health = {
    Normal: { label: "NOMINAL", color: SCADA_COLORS.NORMAL, icon: <CheckCircle2 size={14} /> },
    "Natural Fault": { label: "PHYSICAL FAULT", color: SCADA_COLORS.FAULT, icon: <TriangleAlert size={14} /> },
    "Cyber Intrusion": { label: "CYBER INTRUSION", color: SCADA_COLORS.CYBER, icon: <ShieldAlert size={14} /> },
    "No Data": { label: "NO TELEMETRY", color: SCADA_COLORS.NODATA, icon: <Radio size={14} /> },
  }[verdict];

  const connectionLabel = connectionStatus === "connected" ? "CONNECTED" : connectionStatus === "connecting" ? "RECONNECTING" : "DISCONNECTED";
  const streamLabel = streamStatus === "streaming" ? "STREAMING" : streamStatus === "waiting" ? "WAITING" : streamStatus === "stopped" ? "SIM STOPPED" : streamStatus === "stale" ? "STALE" : streamStatus === "error" ? "ERROR" : "CONNECTING";
  const simTime = latestState?.sim_time || "--:--:--";
  const load = latestState?.true_physical_state?.total_load_mw;
  const estimation = latestState?.state_estimation;

  return (
    <header className="scada-header">
      <div className="scada-brand-block">
        <span className="scada-brand-mark" />
        <div><strong>GridSentinel</strong><span>SCADA / DISCOM operations</span></div>
        <span className="scada-level">L2 / L3</span>
      </div>

      <div className="scada-header-readouts">
        <div className="scada-readout"><Clock3 size={14} /><span>SIM TIME</span><strong>{simTime}</strong></div>
        <div className="scada-readout"><Zap size={14} /><span>LOAD</span><strong>{typeof load === "number" ? `${load.toFixed(2)} MW` : "—"}</strong></div>
        <div className="scada-readout"><Activity size={14} /><span>ESTIMATION</span><strong className={estimation?.success ? "text-normal" : ""}>{estimation ? (estimation.bad_data_detected ? "BAD DATA" : "WLS OK") : "STANDBY"}</strong></div>
        <div className="scada-readout"><Radio size={14} /><span>TELEMETRY</span><strong className={streamStatus === "streaming" ? "text-normal" : "text-fault"}>{streamLabel}</strong></div>
        <div className="scada-health" style={{ color: health.color, borderColor: `${health.color}55`, backgroundColor: `${health.color}12` }}>
          {health.icon}<span>{health.label}</span>
        </div>
      </div>

      <div className={`scada-connection ${connectionStatus}`}>
        {connectionStatus === "connected" ? <Wifi size={14} /> : connectionStatus === "connecting" ? <Radio size={14} /> : <WifiOff size={14} />}
        <span>{connectionLabel}</span><small>/ws/live</small>
      </div>
    </header>
  );
};
