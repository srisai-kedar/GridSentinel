"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  ChevronDown,
  ChevronUp,
  CircleDot,
  FileSpreadsheet,
  Film,
  FastForward,
  Pause,
  Play,
  Radio,
  RotateCcw,
  Upload,
} from "lucide-react";
import { AlertFeed, AlertFeedItem } from "@/components/AlertFeed";
import { AuditLog } from "@/components/AuditLog";
import { ComplianceMap } from "@/components/ComplianceMap";
import { DemoControls } from "@/components/DemoControls";
import { DemoDirector } from "@/components/DemoDirector";
import { EvidencePanel } from "@/components/EvidencePanel";
import { FeederMap } from "@/components/FeederMap";
import { StatusBar } from "@/components/StatusBar";
import { useLiveSocket } from "@/lib/useLiveSocket";
import { useSessionRecorder } from "@/lib/sessionRecorder";
import { useReplayEngine } from "@/lib/replayEngine";
import { AuditLogEntry, LiveSocketPayload } from "@/lib/types";
import {
  getNetworkEvidenceSummary,
  getPhysicsEvidenceSummary,
  getRecommendedAction,
  getRtuAssetLabel,
} from "@/lib/alertText";
import referenceSessionJson from "@/data/reference-session.json";

type WorkspaceTab = "FEED" | "AUDIT" | "CONTROLS" | "DIRECTOR" | "COMPLIANCE";

function formatNumber(value: number | undefined | null, digits = 2, suffix = "") {
  return typeof value === "number" ? `${value.toFixed(digits)}${suffix}` : "—";
}

export default function SCADACommandCenter() {
  const [appMode, setAppMode] = useState<"LIVE" | "REPLAY">("LIVE");
  const [forceMapFallback, setForceMapFallback] = useState(false);
  const [selectedBusId, setSelectedBusId] = useState<number | null>(null);
  const [auditEntries, setAuditEntries] = useState<AuditLogEntry[]>([]);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("FEED");
  const [showBottomDrawer, setShowBottomDrawer] = useState(false);

  const liveSocket = useLiveSocket();
  const sessionRecorder = useSessionRecorder();
  const replayEngine = useReplayEngine(referenceSessionJson as any);

  useEffect(() => {
    if (appMode === "LIVE" && liveSocket.latestState && sessionRecorder.isRecording) {
      sessionRecorder.recordPayload(liveSocket.latestState);
    }
  }, [appMode, liveSocket.latestState, sessionRecorder]);

  const activePayload: LiveSocketPayload | null =
    appMode === "LIVE" ? liveSocket.latestState : replayEngine.currentPayload;
  const activeConnectionStatus =
    appMode === "LIVE" ? liveSocket.connectionStatus : "connected";

  const handleNewVerdictChange = useCallback((item: AlertFeedItem) => {
    setAuditEntries((prev) => [
      {
        id: `audit-${Date.now()}-${item.rtuId}-${Math.random().toString(36).slice(2, 6)}`,
        timestamp: item.wallTimestamp,
        simTime: item.simTime,
        rtuId: item.rtuId,
        assetName: getRtuAssetLabel(item.rtuId),
        classification: item.verdict,
        subtype: item.subtype || "normal",
        confidence: item.confidence,
        networkSummary: getNetworkEvidenceSummary(item.verdict, item.subtype),
        physicsSummary: getPhysicsEvidenceSummary(item.verdict, item.subtype),
        recommendedAction: getRecommendedAction(item.verdict, item.subtype),
        formattedAlert: item.message,
      },
      ...prev,
    ]);
  }, []);

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (loadEvent) => {
      const text = loadEvent.target?.result as string;
      if (text && replayEngine.loadSessionFromJson(text)) setAppMode("REPLAY");
    };
    reader.readAsText(file);
  };

  const counts = useMemo(() => {
    const verdicts = Object.values(activePayload?.ml_verdicts || {});
    return {
      total: verdicts.length,
      normal: verdicts.filter((v) => v.verdict === "Normal").length,
      fault: verdicts.filter((v) => v.verdict === "Natural Fault").length,
      cyber: verdicts.filter((v) => v.verdict === "Cyber Intrusion").length,
    };
  }, [activePayload]);

  const mapFallbackLabel = forceMapFallback ? "Vector map forced" : "Vector map: auto";

  return (
    <div className="scada-shell">
      <StatusBar connectionStatus={activeConnectionStatus} latestState={activePayload} />

      <div className="scada-toolbar">
        <div className="scada-toolbar-group">
          <span className="scada-toolbar-label">Operating mode</span>
          <div className="scada-segmented" role="group" aria-label="Operating mode">
            <button
              className={appMode === "LIVE" ? "is-active is-live" : ""}
              onClick={() => {
                setAppMode("LIVE");
                replayEngine.pause();
              }}
            >
              <Radio size={13} /> Live SCADA
            </button>
            <button
              className={appMode === "REPLAY" ? "is-active is-replay" : ""}
              onClick={() => {
                setAppMode("REPLAY");
                if (!replayEngine.isPlaying) replayEngine.play();
              }}
            >
              <Film size={13} /> Replay
            </button>
          </div>
          {appMode === "REPLAY" && (
            <span data-testid="replay-mode-banner" className="scada-mode-note replay-note">
              Recorded session · not live
            </span>
          )}
        </div>

        <div className="scada-toolbar-group scada-toolbar-right">
          {appMode === "LIVE" ? (
            !sessionRecorder.isRecording ? (
              <button className="scada-tool-button" onClick={sessionRecorder.startRecording}>
                <CircleDot size={13} className="text-cyber" /> Arm recorder
              </button>
            ) : (
              <div className="scada-recording-state">
                <span className="recording-dot" /> Recording · {sessionRecorder.eventCount} frames
                <button
                  onClick={() => {
                    const session = sessionRecorder.stopRecording();
                    sessionRecorder.downloadRecording(session);
                  }}
                >
                  Stop & download
                </button>
              </div>
            )
          ) : (
            <div className="scada-replay-controls" aria-label="Replay controls">
              <button onClick={replayEngine.isPlaying ? replayEngine.pause : replayEngine.play} title={replayEngine.isPlaying ? "Pause replay" : "Play replay"}>
                {replayEngine.isPlaying ? <Pause size={13} /> : <Play size={13} />}
              </button>
              <button onClick={replayEngine.stop} title="Restart replay"><RotateCcw size={13} /></button>
              <input
                aria-label="Replay position"
                type="range"
                min={0}
                max={100}
                value={replayEngine.progressPercent}
                onChange={(event) => replayEngine.seekToPercent(Number(event.target.value))}
              />
              <span>{replayEngine.currentIndex + 1}/{replayEngine.totalEvents}</span>
              <FastForward size={13} />
              {[1, 2, 5].map((speed) => (
                <button
                  key={speed}
                  className={replayEngine.playbackSpeed === speed ? "speed-active" : ""}
                  onClick={() => replayEngine.setPlaybackSpeed(speed)}
                >{speed}×</button>
              ))}
              <label className="scada-upload" title="Load a recorded session">
                <Upload size={13} />
                <input type="file" accept=".json" onChange={handleFileUpload} />
              </label>
            </div>
          )}
          <button
            className={`scada-tool-button ${forceMapFallback ? "is-warning" : ""}`}
            onClick={() => setForceMapFallback((current) => !current)}
            title="Toggle the offline vector map"
          >
            {mapFallbackLabel}
          </button>
        </div>
      </div>

      <main className="scada-main">
        <section className="scada-workspace">
          <div className="scada-overview">
            <div>
              <span className="scada-kicker">Operations overview</span>
              <h1>11 kV radial feeder</h1>
              <p>GridSentinel-Feeder · live topology and physics-aware anomaly triage</p>
            </div>
            <div className="scada-overview-stats">
              <div><span>RTUs online</span><strong>{counts.total ? `${counts.total}/5` : "—"}</strong></div>
              <div><span>Nominal</span><strong className="text-normal">{counts.normal || "—"}</strong></div>
              <div><span>Faults</span><strong className="text-fault">{counts.fault || "—"}</strong></div>
              <div><span>Cyber</span><strong className="text-cyber">{counts.cyber || "—"}</strong></div>
            </div>
          </div>

          <div className="scada-metrics" aria-label="Feeder measurements">
            <div><span>Feeder load</span><strong>{formatNumber(activePayload?.true_physical_state.total_load_mw, 2, " MW")}</strong><small>system total</small></div>
            <div><span>Losses</span><strong>{formatNumber(activePayload?.true_physical_state.total_loss_mw, 3, " MW")}</strong><small>calculated network loss</small></div>
            <div><span>Power flow</span><strong className={activePayload?.power_flow_converged ? "text-normal" : "text-fault"}>{activePayload ? (activePayload.power_flow_converged ? "Converged" : "Not converged") : "Standby"}</strong><small>pandapower solution</small></div>
            <div><span>State estimation</span><strong className={activePayload?.state_estimation.success ? "text-normal" : "text-fault"}>{activePayload ? (activePayload.state_estimation.success ? "WLS converged" : "Standby") : "Standby"}</strong><small>{activePayload?.state_estimation.bad_data_detected ? "bad data flagged" : "χ² residual check"}</small></div>
          </div>

          <section className="scada-surface scada-topology-panel">
            <div className="scada-section-header">
              <div>
                <span className="scada-kicker">Primary workspace</span>
                <h2>Feeder topology</h2>
              </div>
              <div className="scada-section-meta"><Activity size={13} /> click a bus to inspect telemetry</div>
            </div>
            <div className="scada-map-frame">
              <FeederMap
                latestState={activePayload}
                selectedBusId={selectedBusId}
                onSelectBus={setSelectedBusId}
                forceFallback={forceMapFallback}
                onToggleForceFallback={() => setForceMapFallback((current) => !current)}
              />
            </div>
          </section>

          <section className={`scada-surface scada-audit-drawer ${showBottomDrawer ? "is-open" : ""}`}>
            <button className="scada-drawer-toggle" onClick={() => setShowBottomDrawer((current) => !current)} aria-expanded={showBottomDrawer}>
              <span><FileSpreadsheet size={14} /><span>Incident audit trail</span><em>{auditEntries.length} events</em></span>
              <span>{showBottomDrawer ? "Collapse" : "Open log"} {showBottomDrawer ? <ChevronDown size={14} /> : <ChevronUp size={14} />}</span>
            </button>
            {showBottomDrawer && <div className="scada-audit-content"><AuditLog entries={auditEntries} onClearLogs={() => setAuditEntries([])} /></div>}
          </section>
        </section>

        <aside className="scada-sidebar">
          <div className="scada-sidebar-tabs" role="tablist" aria-label="Operations panels">
            {([
              ["FEED", "Incidents"],
              ["AUDIT", "Audit"],
              ["CONTROLS", "Scenario"],
              ["DIRECTOR", "Demo"],
              ["COMPLIANCE", "CEA-2026"],
            ] as [WorkspaceTab, string][]).map(([tab, label]) => (
              <button key={tab} className={activeTab === tab ? "is-active" : ""} onClick={() => setActiveTab(tab)} role="tab" aria-selected={activeTab === tab}>
                {label}{tab === "AUDIT" && auditEntries.length > 0 ? ` · ${auditEntries.length}` : ""}
              </button>
            ))}
          </div>

          <div className="scada-sidebar-content">
            {activeTab === "FEED" && (
              <div className="scada-feed-stack">
                <div className="scada-surface scada-alert-summary">
                  <div><span className="scada-kicker">Current assessment</span><strong>{counts.cyber ? "Cyber intrusion" : counts.fault ? "Natural fault" : activePayload ? "Nominal operation" : "Awaiting telemetry"}</strong></div>
                  <span className={`state-marker ${counts.cyber ? "cyber" : counts.fault ? "fault" : activePayload ? "normal" : "nodata"}`} />
                </div>
                <div className="scada-alert-container">
                  <AlertFeed latestState={activePayload} onAlertClick={(rtuId) => setSelectedBusId(rtuId)} onNewVerdictChange={handleNewVerdictChange} />
                </div>
                <EvidencePanel latestState={activePayload} selectedBusId={selectedBusId} />
              </div>
            )}
            {activeTab === "AUDIT" && <AuditLog entries={auditEntries} onClearLogs={() => setAuditEntries([])} />}
            {activeTab === "CONTROLS" && <DemoControls latestState={activePayload} isReplayMode={appMode === "REPLAY"} />}
            {activeTab === "DIRECTOR" && <DemoDirector onNavigateTab={(tab) => setActiveTab(tab as WorkspaceTab)} isReplayMode={appMode === "REPLAY"} />}
            {activeTab === "COMPLIANCE" && <ComplianceMap />}
          </div>
        </aside>
      </main>
    </div>
  );
}
