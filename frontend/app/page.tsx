"use client";

import React, { useState, useCallback, useEffect, useRef } from "react";
import { useLiveSocket } from "@/lib/useLiveSocket";
import { useSessionRecorder } from "@/lib/sessionRecorder";
import { useReplayEngine } from "@/lib/replayEngine";
import { StatusBar } from "@/components/StatusBar";
import { FeederMap } from "@/components/FeederMap";
import { AlertFeed, AlertFeedItem } from "@/components/AlertFeed";
import { AuditLog } from "@/components/AuditLog";
import { DemoControls } from "@/components/DemoControls";
import { DemoDirector } from "@/components/DemoDirector";
import { ComplianceMap } from "@/components/ComplianceMap";
import { AuditLogEntry, LiveSocketPayload } from "@/lib/types";
import {
  getNetworkEvidenceSummary,
  getPhysicsEvidenceSummary,
  getRecommendedAction,
  getRtuAssetLabel,
} from "@/lib/alertText";
import referenceSessionJson from "@/data/reference-session.json";
import {
  Activity,
  Award,
  BookOpen,
  ChevronDown,
  ChevronUp,
  CircleDot,
  Download,
  FastForward,
  FileSpreadsheet,
  Film,
  Layers,
  MapPin,
  Maximize2,
  Pause,
  Play,
  Radio,
  RotateCcw,
  Scale,
  Shield,
  Sliders,
  Sparkles,
  Upload,
  Video,
} from "lucide-react";

export default function SCADACommandCenter() {
  const [appMode, setAppMode] = useState<"LIVE" | "REPLAY">("LIVE");
  const [forceMapFallback, setForceMapFallback] = useState<boolean>(false);
  const [selectedBusId, setSelectedBusId] = useState<number | null>(null);
  const [auditEntries, setAuditEntries] = useState<AuditLogEntry[]>([]);
  const [activeTab, setActiveTab] = useState<
    "FEED" | "AUDIT" | "CONTROLS" | "DIRECTOR" | "COMPLIANCE"
  >("FEED");
  const [showBottomDrawer, setShowBottomDrawer] = useState<boolean>(false);

  // Live WebSocket source
  const liveSocket = useLiveSocket();

  // Session Recorder
  const sessionRecorder = useSessionRecorder();

  // Replay Engine
  const replayEngine = useReplayEngine(referenceSessionJson as any);

  // Record incoming live messages if recording is armed
  useEffect(() => {
    if (appMode === "LIVE" && liveSocket.latestState && sessionRecorder.isRecording) {
      sessionRecorder.recordPayload(liveSocket.latestState);
    }
  }, [appMode, liveSocket.latestState, sessionRecorder]);

  // Unified telemetry payload consumed by all components
  const activePayload: LiveSocketPayload | null =
    appMode === "LIVE" ? liveSocket.latestState : replayEngine.currentPayload;

  // Unified connection status consumed by StatusBar
  const activeConnectionStatus =
    appMode === "LIVE" ? liveSocket.connectionStatus : "connected";

  // Accumulate audit log entries on verdict state transition
  const handleNewVerdictChange = useCallback((item: AlertFeedItem) => {
    const assetName = getRtuAssetLabel(item.rtuId);
    const networkSummary = getNetworkEvidenceSummary(item.verdict, item.subtype);
    const physicsSummary = getPhysicsEvidenceSummary(item.verdict, item.subtype);
    const recommendedAction = getRecommendedAction(item.verdict, item.subtype);

    const newAuditEntry: AuditLogEntry = {
      id: `audit-${Date.now()}-${item.rtuId}-${Math.random().toString(36).substr(2, 4)}`,
      timestamp: item.wallTimestamp,
      simTime: item.simTime,
      rtuId: item.rtuId,
      assetName,
      classification: item.verdict,
      subtype: item.subtype || "normal",
      confidence: item.confidence,
      networkSummary,
      physicsSummary,
      recommendedAction,
      formattedAlert: item.message,
    };

    setAuditEntries((prev) => [newAuditEntry, ...prev]);
  }, []);

  const handleClearAuditLogs = useCallback(() => {
    setAuditEntries([]);
  }, []);

  const handleAlertClick = useCallback((rtuId: number) => {
    const rtuToBus: Record<number, number> = {
      1: 1,
      2: 2,
      3: 3,
      4: 4,
      5: 5,
    };
    setSelectedBusId(rtuToBus[rtuId] || rtuId);
  }, []);

  // File upload for custom session replay
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      if (text) {
        const success = replayEngine.loadSessionFromJson(text);
        if (success) {
          setAppMode("REPLAY");
        }
      }
    };
    reader.readAsText(file);
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-[#08090D] text-[#EDEDF0] overflow-hidden select-none">
      {/* Top Status Bar */}
      <StatusBar
        connectionStatus={activeConnectionStatus}
        latestState={activePayload}
      />

      {/* Mode Control & Persistent Banner */}
      <div className="w-full bg-[#0E1118] border-b border-white/[0.07] px-4 py-1.5 flex flex-wrap items-center justify-between gap-2 text-xs">
        {/* Left: Mode Switcher & Replay Banner */}
        <div className="flex items-center space-x-3">
          <div className="flex items-center bg-[#131722] rounded-[6px] p-0.5 border border-white/[0.06]">
            <button
              onClick={() => {
                setAppMode("LIVE");
                replayEngine.pause();
              }}
              className={`px-3 py-1 rounded-[4px] font-medium text-[11px] transition flex items-center space-x-1.5 ${
                appMode === "LIVE"
                  ? "bg-[#181E2C] text-[#10B981] border border-[#10B981]/30 font-semibold"
                  : "text-[#5A6275] hover:text-[#9CA3AF]"
              }`}
            >
              <Radio className="w-3.5 h-3.5" />
              <span>LIVE SCADA</span>
            </button>
            <button
              onClick={() => {
                setAppMode("REPLAY");
                if (!replayEngine.isPlaying) {
                  replayEngine.play();
                }
              }}
              className={`px-3 py-1 rounded-[4px] font-medium text-[11px] transition flex items-center space-x-1.5 ${
                appMode === "REPLAY"
                  ? "bg-[#181E2C] text-[#A78BFA] border border-[#8B5CF6]/40 font-semibold"
                  : "text-[#5A6275] hover:text-[#9CA3AF]"
              }`}
            >
              <Film className="w-3.5 h-3.5" />
              <span>REPLAY MODE</span>
            </button>
          </div>

          {/* UNMISSABLE Persistent Banner in Replay Mode */}
          {appMode === "REPLAY" && (
            <div
              data-testid="replay-mode-banner"
              className="flex items-center space-x-2 px-3 py-1 rounded-[6px] bg-[#131722] border border-[#8B5CF6]/40 text-[#A78BFA] font-mono font-semibold text-[11px] animate-pulse"
            >
              <span className="w-2 h-2 rounded-full bg-[#A78BFA]"></span>
              <span>REPLAY MODE — recorded session, not live</span>
            </div>
          )}
        </div>

        {/* Center / Right: Live Recording / Replay Controls */}
        <div className="flex items-center space-x-2">
          {appMode === "LIVE" ? (
            /* Live Recording Toolbar */
            <div className="flex items-center space-x-2">
              {!sessionRecorder.isRecording ? (
                <button
                  onClick={sessionRecorder.startRecording}
                  className="flex items-center space-x-1.5 bg-[#131722] hover:bg-[#181E2C] text-[#EDEDF0] border border-white/[0.08] hover:border-[#EF4444]/40 px-2.5 py-1 rounded-[6px] transition text-[11px] font-medium"
                  title="Arm session recorder to capture live telemetry"
                >
                  <CircleDot className="w-3.5 h-3.5 text-[#EF4444] animate-pulse" />
                  <span>Record Session</span>
                </button>
              ) : (
                <div className="flex items-center space-x-2 bg-[#131722] border border-[#EF4444]/50 px-2.5 py-1 rounded-[6px] text-[#EDEDF0] text-[11px] font-mono">
                  <span className="animate-ping w-2 h-2 rounded-full bg-[#EF4444]"></span>
                  <span>Recording ({sessionRecorder.eventCount} msgs)</span>
                  <button
                    onClick={() => {
                      const sess = sessionRecorder.stopRecording();
                      sessionRecorder.downloadRecording(sess);
                    }}
                    className="ml-1 bg-[#EF4444] hover:bg-[#DC2626] text-white px-2 py-0.5 rounded-[4px] text-[10px] font-semibold"
                  >
                    Stop & Download
                  </button>
                </div>
              )}
            </div>
          ) : (
            /* Replay Controls Toolbar */
            <div className="flex items-center space-x-2 bg-[#131722] px-2.5 py-1 rounded-[6px] border border-white/[0.06] text-[11px]">
              {/* Play / Pause */}
              {!replayEngine.isPlaying ? (
                <button
                  onClick={replayEngine.play}
                  className="text-[#A78BFA] hover:text-white p-1 rounded"
                  title="Play recorded session"
                >
                  <Play className="w-3.5 h-3.5 fill-[#A78BFA]" />
                </button>
              ) : (
                <button
                  onClick={replayEngine.pause}
                  className="text-[#F59E0B] hover:text-white p-1 rounded"
                  title="Pause playback"
                >
                  <Pause className="w-3.5 h-3.5" />
                </button>
              )}

              <button
                onClick={replayEngine.stop}
                className="text-[#5A6275] hover:text-[#EDEDF0] p-1 rounded"
                title="Restart playback"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>

              {/* Scrubber Slider */}
              <div className="flex items-center space-x-1.5 font-mono">
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={replayEngine.progressPercent}
                  onChange={(e) =>
                    replayEngine.seekToPercent(parseFloat(e.target.value))
                  }
                  className="w-24 md:w-36 h-1.5 bg-[#181E2C] rounded-lg appearance-none cursor-pointer accent-[#8B5CF6]"
                />
                <span className="text-[#A78BFA] text-[10px]">
                  {replayEngine.currentIndex + 1}/{replayEngine.totalEvents}
                </span>
              </div>

              {/* Speed Multiplier */}
              <div className="flex items-center space-x-1 border-l border-white/[0.08] pl-2">
                <FastForward className="w-3.5 h-3.5 text-[#5A6275]" />
                {[1, 2, 5].map((spd) => (
                  <button
                    key={spd}
                    onClick={() => replayEngine.setPlaybackSpeed(spd)}
                    className={`px-1.5 py-0.5 rounded-[4px] text-[10px] font-mono ${
                      replayEngine.playbackSpeed === spd
                        ? "bg-[#8B5CF6] text-white font-bold"
                        : "text-[#5A6275] hover:text-[#9CA3AF]"
                    }`}
                  >
                    {spd}x
                  </button>
                ))}
              </div>

              {/* File Upload Input */}
              <label className="cursor-pointer text-[#5A6275] hover:text-[#A78BFA] border-l border-white/[0.08] pl-2">
                <Upload className="w-3.5 h-3.5" />
                <input
                  type="file"
                  accept=".json"
                  onChange={handleFileUpload}
                  className="hidden"
                />
              </label>
            </div>
          )}

          {/* Quick Trigger for Fallback View */}
          <button
            onClick={() => setForceMapFallback(!forceMapFallback)}
            className={`px-2 py-1 rounded-[6px] text-[10px] font-mono border transition ${
              forceMapFallback
                ? "bg-[#131722] text-[#F59E0B] border-[#F59E0B]/40"
                : "bg-[#131722] text-[#5A6275] border-white/[0.06] hover:text-[#9CA3AF]"
            }`}
            title="Toggle SVG/Vector Fallback map for offline simulation"
          >
            {forceMapFallback ? "Fallback: Forced ON" : "Fallback: Auto"}
          </button>
        </div>
      </div>

      {/* Main Command Center Grid */}
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-3 p-3 overflow-hidden">
        {/* Left / Center Section: Map & Bottom Drawer (8 cols) */}
        <div className="lg:col-span-8 flex flex-col h-full space-y-3 overflow-hidden">
          {/* Feeder Map Component */}
          <div className="flex-1 relative overflow-hidden rounded-[10px] border border-white/[0.07] min-h-[360px] bg-[#0E1118]">
            <FeederMap
              latestState={activePayload}
              selectedBusId={selectedBusId}
              onSelectBus={(busIdx) => setSelectedBusId(busIdx)}
              forceFallback={forceMapFallback}
              onToggleForceFallback={() => setForceMapFallback(!forceMapFallback)}
            />
          </div>

          {/* Bottom Audit Log Drawer / Toggle Bar */}
          <div className="bg-[#0E1118] border border-white/[0.07] rounded-[10px] overflow-hidden flex flex-col transition-all duration-300">
            <div
              onClick={() => setShowBottomDrawer(!showBottomDrawer)}
              className="p-2.5 bg-[#0E1118] flex items-center justify-between cursor-pointer hover:bg-[#131722] transition text-xs select-none"
            >
              <div className="flex items-center space-x-2">
                <FileSpreadsheet className="w-4 h-4 text-[#10B981]" />
                <span className="font-bold text-[#EDEDF0] uppercase tracking-wider text-[11px]">
                  CEA-2026 Incident Audit Trail Log
                </span>
                <span className="text-[10px] px-1.5 py-0.5 rounded-[4px] bg-[#131722] text-[#10B981] font-mono border border-white/[0.06]">
                  {auditEntries.length} Records
                </span>
              </div>

              <div className="flex items-center space-x-2 text-[#5A6275] text-[11px]">
                <span>{showBottomDrawer ? "Collapse Panel" : "Expand Table"}</span>
                {showBottomDrawer ? (
                  <ChevronDown className="w-4 h-4" />
                ) : (
                  <ChevronUp className="w-4 h-4" />
                )}
              </div>
            </div>

            {showBottomDrawer && (
              <div className="h-64 p-2 overflow-hidden border-t border-white/[0.07]">
                <AuditLog
                  entries={auditEntries}
                  onClearLogs={handleClearAuditLogs}
                />
              </div>
            )}
          </div>
        </div>

        {/* Right Section: Multi-Tab Panel (4 cols) */}
        <div className="lg:col-span-4 flex flex-col h-full space-y-3 overflow-hidden">
          {/* Right Top Tab Switcher */}
          <div className="flex bg-[#131722] p-1 rounded-[8px] border border-white/[0.07] text-[11px] select-none">
            <button
              onClick={() => setActiveTab("FEED")}
              className={`flex-1 py-1.5 rounded-[6px] font-medium transition text-center ${
                activeTab === "FEED"
                  ? "bg-[#181E2C] text-[#EDEDF0] border border-[#8B5CF6]/40 shadow-sm font-semibold"
                  : "text-[#5A6275] hover:text-[#9CA3AF]"
              }`}
            >
              Alerts
            </button>
            <button
              onClick={() => setActiveTab("DIRECTOR")}
              className={`flex-1 py-1.5 rounded-[6px] font-medium transition text-center ${
                activeTab === "DIRECTOR"
                  ? "bg-[#181E2C] text-[#EDEDF0] border border-[#8B5CF6]/40 shadow-sm font-semibold"
                  : "text-[#5A6275] hover:text-[#9CA3AF]"
              }`}
            >
              Director
            </button>
            <button
              onClick={() => setActiveTab("CONTROLS")}
              className={`flex-1 py-1.5 rounded-[6px] font-medium transition text-center ${
                activeTab === "CONTROLS"
                  ? "bg-[#181E2C] text-[#EDEDF0] border border-[#8B5CF6]/40 shadow-sm font-semibold"
                  : "text-[#5A6275] hover:text-[#9CA3AF]"
              }`}
            >
              Controls
            </button>
            <button
              onClick={() => setActiveTab("AUDIT")}
              className={`flex-1 py-1.5 rounded-[6px] font-medium transition text-center ${
                activeTab === "AUDIT"
                  ? "bg-[#181E2C] text-[#EDEDF0] border border-[#8B5CF6]/40 shadow-sm font-semibold"
                  : "text-[#5A6275] hover:text-[#9CA3AF]"
              }`}
            >
              Audit ({auditEntries.length})
            </button>
            <button
              onClick={() => setActiveTab("COMPLIANCE")}
              className={`flex-1 py-1.5 rounded-[6px] font-medium transition text-center ${
                activeTab === "COMPLIANCE"
                  ? "bg-[#181E2C] text-[#EDEDF0] border border-[#8B5CF6]/40 shadow-sm font-semibold"
                  : "text-[#5A6275] hover:text-[#9CA3AF]"
              }`}
            >
              CEA-2026
            </button>
          </div>

          {/* Tab Content Panes */}
          <div className="flex-1 overflow-hidden">
            {activeTab === "FEED" && (
              <AlertFeed
                latestState={activePayload}
                onAlertClick={handleAlertClick}
                onNewVerdictChange={handleNewVerdictChange}
              />
            )}

            {activeTab === "DIRECTOR" && (
              <DemoDirector
                onNavigateTab={(tab) => setActiveTab(tab as any)}
                isReplayMode={appMode === "REPLAY"}
              />
            )}

            {activeTab === "CONTROLS" && (
              <DemoControls
                latestState={activePayload}
                isReplayMode={appMode === "REPLAY"}
              />
            )}

            {activeTab === "AUDIT" && (
              <AuditLog
                entries={auditEntries}
                onClearLogs={handleClearAuditLogs}
              />
            )}

            {activeTab === "COMPLIANCE" && <ComplianceMap />}
          </div>
        </div>
      </main>
    </div>
  );
}
