"use client";

import React, { useState, useCallback } from "react";
import { useLiveSocket } from "@/lib/useLiveSocket";
import { StatusBar } from "@/components/StatusBar";
import { FeederMap } from "@/components/FeederMap";
import { AlertFeed, AlertFeedItem } from "@/components/AlertFeed";
import { AuditLog } from "@/components/AuditLog";
import { DemoControls } from "@/components/DemoControls";
import { AuditLogEntry } from "@/lib/types";
import {
  getNetworkEvidenceSummary,
  getPhysicsEvidenceSummary,
  getRecommendedAction,
  getRtuAssetLabel,
} from "@/lib/alertText";
import {
  Activity,
  ChevronDown,
  ChevronUp,
  FileSpreadsheet,
  Layers,
  MapPin,
  Maximize2,
  Radio,
  Shield,
  Sliders,
} from "lucide-react";

export default function SCADACommandCenter() {
  const { latestState, connectionStatus, recentTrafficEvents } = useLiveSocket();

  const [selectedBusId, setSelectedBusId] = useState<number | null>(null);
  const [auditEntries, setAuditEntries] = useState<AuditLogEntry[]>([]);
  const [activeTab, setActiveTab] = useState<"FEED" | "AUDIT" | "CONTROLS">("FEED");
  const [showBottomDrawer, setShowBottomDrawer] = useState<boolean>(false);

  // Accumulate audit log entries on verdict change
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
    // Map RTU to bus index
    const rtuToBus: Record<number, number> = {
      1: 1,
      2: 2,
      3: 3,
      4: 4,
      5: 5,
    };
    const busIdx = rtuToBus[rtuId] || rtuId;
    setSelectedBusId(busIdx);
  }, []);

  return (
    <div className="flex flex-col h-screen w-screen bg-[#0B0F19] text-gray-100 overflow-hidden select-none">
      {/* Top Status Bar */}
      <StatusBar
        connectionStatus={connectionStatus}
        latestState={latestState}
      />

      {/* Main Command Center Grid */}
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-3 p-3 overflow-hidden">
        {/* Left / Center Section: Map & Bottom Expandable Drawer (8 cols on large screens) */}
        <div className="lg:col-span-8 flex flex-col h-full space-y-3 overflow-hidden">
          {/* Feeder Map Component */}
          <div className="flex-1 relative overflow-hidden rounded-lg min-h-[360px]">
            <FeederMap
              latestState={latestState}
              selectedBusId={selectedBusId}
              onSelectBus={(busIdx) => setSelectedBusId(busIdx)}
            />
          </div>

          {/* Bottom Audit Log Drawer / Toggle Bar */}
          <div className="bg-[#0F172A] border border-gray-800 rounded-lg overflow-hidden flex flex-col transition-all duration-300">
            {/* Bar Toggle Header */}
            <div
              onClick={() => setShowBottomDrawer(!showBottomDrawer)}
              className="p-2.5 bg-[#0B0F19] flex items-center justify-between cursor-pointer hover:bg-[#131B2E] transition text-xs select-none"
            >
              <div className="flex items-center space-x-2">
                <FileSpreadsheet className="w-4 h-4 text-emerald-400" />
                <span className="font-bold text-gray-200 uppercase tracking-wider">
                  CEA-2026 Incident Audit Trail Log
                </span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-emerald-300 font-mono">
                  {auditEntries.length} Records
                </span>
              </div>

              <div className="flex items-center space-x-2 text-gray-400 text-[11px]">
                <span>{showBottomDrawer ? "Collapse Panel" : "Expand Table"}</span>
                {showBottomDrawer ? (
                  <ChevronDown className="w-4 h-4" />
                ) : (
                  <ChevronUp className="w-4 h-4" />
                )}
              </div>
            </div>

            {/* Expandable Audit Log Table */}
            {showBottomDrawer && (
              <div className="h-64 p-2 overflow-hidden">
                <AuditLog
                  entries={auditEntries}
                  onClearLogs={handleClearAuditLogs}
                />
              </div>
            )}
          </div>
        </div>

        {/* Right Section: Alert Feed & Demo Controls (4 cols on large screens) */}
        <div className="lg:col-span-4 flex flex-col h-full space-y-3 overflow-hidden">
          {/* Right Top Tab Switcher */}
          <div className="flex bg-[#0F172A] p-1 rounded-lg border border-gray-800 text-xs select-none">
            <button
              onClick={() => setActiveTab("FEED")}
              className={`flex-1 py-1.5 rounded-md font-semibold transition text-center ${
                activeTab === "FEED"
                  ? "bg-cyan-950 text-cyan-300 border border-cyan-700/60 shadow"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              Alert Feed
            </button>
            <button
              onClick={() => setActiveTab("CONTROLS")}
              className={`flex-1 py-1.5 rounded-md font-semibold transition text-center ${
                activeTab === "CONTROLS"
                  ? "bg-cyan-950 text-cyan-300 border border-cyan-700/60 shadow"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              Demo Controls
            </button>
            <button
              onClick={() => setActiveTab("AUDIT")}
              className={`flex-1 py-1.5 rounded-md font-semibold transition text-center ${
                activeTab === "AUDIT"
                  ? "bg-cyan-950 text-cyan-300 border border-cyan-700/60 shadow"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              Audit Log ({auditEntries.length})
            </button>
          </div>

          {/* Tab Content Panes */}
          <div className="flex-1 overflow-hidden">
            {activeTab === "FEED" && (
              <AlertFeed
                latestState={latestState}
                onAlertClick={handleAlertClick}
                onNewVerdictChange={handleNewVerdictChange}
              />
            )}

            {activeTab === "CONTROLS" && (
              <DemoControls latestState={latestState} />
            )}

            {activeTab === "AUDIT" && (
              <AuditLog
                entries={auditEntries}
                onClearLogs={handleClearAuditLogs}
              />
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
